from django.http import HttpResponse
from django.template import loader
from django.views.generic import ListView
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
#from .forms import StoreSelectionForm
from django.utils.safestring import mark_safe 
from django.contrib import messages
from doughsaverapp.models import *
from django.urls import reverse
from django.db import connection
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from matplotlib.dates import DateFormatter
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from django.conf import settings
from django.contrib.auth.decorators import login_required

@login_required
def user_ingredients(request):
    # Retrieve the currently logged-in user
    user = request.user

    # Retrieve the ingredients associated with the user
    user_ingredients = Ingredient.objects.filter(ingredientcollection__UserID=user)

    # Pass the data to the template
    return render(request, 'user_ingredients.html', {'user_ingredients': user_ingredients})
    

def get_price_history(ingredient_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT StoreID, UpdateTimestamp, HistoricalPrice
            FROM PriceHistory
            WHERE IngredientID = %s
              AND YEAR(UpdateTimestamp) = 2024
            ORDER BY UpdateTimestamp
            """,
            [ingredient_id]
        )
        rows = cursor.fetchall()
    return rows

def plot_price_history(ingredient_name, price_history, plot_save_path):
    # Create a dictionary to store data for each store
    store_data = {}

    for row in price_history:
        store_id, timestamp, price = row

        # Convert timestamps to datetime objects
        timestamp = pd.to_datetime(timestamp)

        # If the store_id is not in the dictionary, create a new entry
        if store_id not in store_data:
            store_data[store_id] = {'timestamps': [], 'prices': [], 'label': f'Store {store_id}'}

        # Append data to the corresponding store entry
        store_data[store_id]['timestamps'].append(timestamp)
        store_data[store_id]['prices'].append(price)

    # Retrieve store names from the database
    store_names = {store.StoreId: store.StoreName for store in GroceryStore.objects.all()}

    # Create the plot
    fig, ax = plt.subplots(figsize=(14, 8))

    for store_id, data in store_data.items():
        # Use store names in the legend
        store_name = store_names.get(store_id, f'Store {store_id}')

        # Combine timestamps and prices into a DataFrame
        df = pd.DataFrame({'timestamps': data['timestamps'], 'prices': data['prices']})
        df.set_index('timestamps', inplace=True)

        # Resample data to fill in missing timestamps with the last known price
        df_resampled = df.resample('D').fillna(method='ffill')
        

        # Handle any remaining NaN values after forward fill
        df_resampled['prices'].fillna(method='bfill', inplace=True)

        # Ensure there are no NaN values in the DataFrame
        df_resampled.dropna(subset=['prices'], inplace=True)


        # Extend the last known price to cover the entire year
        last_known_price = df_resampled['prices'].iloc[-1]
        end_of_year = pd.to_datetime(f'2024-12-31')
        
        # Create a new DataFrame for the end of the year with the last known price
        df_end_of_year = pd.DataFrame({'prices': [last_known_price]}, index=[end_of_year])
        
        # Extend the first known price to cover the entire year
        first_known_price = df_resampled['prices'].iloc[0]
        start_of_year = pd.to_datetime(f'2024-01-01')
        
        # Create a new DataFrame for the start of the year with the first known price
        df_start_of_year = pd.DataFrame({'prices': [first_known_price]}, index=[start_of_year])

        # Concatenate the DataFrames to combine the original data and start-of-year data
        df_resampled = pd.concat([df_start_of_year, df_resampled])

        # Concatenate the DataFrames to combine the original data and end-of-year data
        df_resampled = pd.concat([df_resampled, df_end_of_year])

        # Plot the data
        ax.plot(df_resampled.index, df_resampled['prices'], label=store_name)

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(DateFormatter('%m-%Y'))
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.set_title(f'Price History for {ingredient_name}')
    ax.legend()
    # Rotate x-axis labels vertically
    plt.xticks(rotation='vertical')
    # Add a grid
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.7)

    # Save the plot as an image
    plt.savefig(plot_save_path)
    plt.close()  # Close the plot to free up resources

def ingredient_price_history(request, ingredient_id):
    # Get the ingredient name from the Ingredient table
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT IngredientName FROM Ingredient WHERE IngredientID = %s",
            [ingredient_id]
        )
        ingredient_name = cursor.fetchone()[0]

    # Get the price history for the current ingredient
    price_history = get_price_history(ingredient_id)

    # Define the path to save the Matplotlib plot image
    plot_save_path = f"media/plots/{ingredient_id}_price_history.png"

    # Plot the price history and save the image
    plot_price_history(ingredient_name, price_history, plot_save_path)

    # Pass the image file path to the template
    context = {
        'ingredient_name': ingredient_name,
        'plot_image_path': plot_save_path,
    }

    # Render the template
    return render(request, 'price_history/ingredient_price_history.html', context)

def index(request):
    if request.method == "POST":
        username = request.POST["uname"]
        password = request.POST["psw"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Redirect to a success page.
            messages.success(request, mark_safe("Welcome, you have successfully logged in!<br>"))
            return redirect('index') #uses name ='index' from urls.py
        else:
            # Return an 'invalid login' error message.
            messages.success(request, mark_safe("Incorrect username or password, please try again.<br>"))
            return redirect('index')
    else:
        return render(request, 'index.html', {})
    
def logout_user(request):
    logout(request)
    messages.success(request, mark_safe("You were successfully logged out.<br>"))
    return redirect('index')

def accountcreation(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data['username']
            password = form.cleaned_data['password1']
            user = authenticate(username=username, password=password)
            login(request, user)
            messages.success(request, mark_safe("You were successfully registered.<br>"))
            return redirect('index')
    else:
        form = UserCreationForm()
    return render(request, 'accountcreation.html', {'form': form})

def store_selection(request):
    if request.method == 'POST':
        selected_store_ids = request.POST.getlist('store_ids')
        user_id = request.user.id
        StoreCollection.objects.filter(UserID=user_id).delete()
        for store_id in selected_store_ids:
            StoreCollection.objects.create(UserID_id=user_id, StoreID_id=store_id)
    
        return redirect('price_comparison_options')

    grocery_stores = GroceryStore.objects.all()

    return render(request, 'store_selection.html', {'grocery_stores': grocery_stores})

def price_comparison_options(request):
    if request.method == 'POST':
        #save the checkbox values in a list
        selected_price_options = request.POST.getlist('pricing_options')
        #If more than one price option is selected, error (Please choose one option)
        if len(selected_price_options) > 1:
            messages.error(request, mark_safe("Please choose only one price comparison option.<br><br>"))
            return redirect('price_comparison_options')
        else:
            #check which pricing option it is
            #call another function to get/pass stores and shopping list to correct pricing algorithm 
            #redirect to cost breakdown?
            return redirect('price_comparison_options')
        
    user_id = request.user.id
    user_stores = StoreCollection.objects.filter(UserID=user_id).values('StoreID')
    return render(request, 'price_comparison.html', {'user_stores': user_stores})

def view_selected_stores(request):
    user_id = request.user.id
    user_stores = StoreCollection.objects.filter(UserID=user_id).values('StoreID__StoreName', 'StoreID__Address')
    return render(request, 'view_stores.html', {'user_stores': user_stores})

class PriceDataListView(ListView):
    model = PriceData
    template_name = 'price_data_list.html'
    context_object_name = 'price_data_list'

def ingredient_list(request):
    ingredients = Ingredient.objects.all()  # Query all Ingredient objects
    context = {'ingredients': ingredients}
    return render(request, 'ingredient_list.html', context)
    
def current_prices(request):
    # Retrieve PriceData objects along with related GroceryStore and Ingredient
    price_data_list = PriceData.objects.select_related('store', 'ingredient').all()
    context = {'price_data_list': price_data_list}
    return render(request, 'current_prices.html', context)

def price_history_list(request):
    price_history_list = PriceHistory.objects.all()
    context = {'price_history_list': price_history_list}
    return render(request, 'price_history_list.html', context)

def ingredient_search(request):
    search_query = request.GET.get('search_query', '')
    items = []

    if search_query:
            items = PriceData.objects.filter(IngredientID__IngredientName__icontains=search_query).values(
            'IngredientID',
            'IngredientID__IngredientName',
            'CurrentPrice',
            'StoreID__StoreName'
            )
    else:
        # Fetch all items from PriceData table if no search query is provided
        items = PriceData.objects.all().values(
            'IngredientID',
            'IngredientID__IngredientName',
            'CurrentPrice',
            'StoreID__StoreName'
        )

    return render(request, 'ingredient_search.html', {'ingredient_search_query': search_query, 'items': items})
    
def get_current_prices(ingredient_id):
    current_prices = PriceData.objects.filter(IngredientID=ingredient_id)
    return current_prices
    
def ingredient_detail(request, IngredientID):

    # Get the ingredient object or return a 404 error if not found
    ingredient = get_object_or_404(Ingredient, pk=IngredientID)

    # Get the price history for the current ingredient
    price_history = get_price_history(IngredientID)
    
    # Get the current prices for the current ingredient
    current_prices = get_current_prices(IngredientID)
    
    # Define the path to save the Matplotlib plot image
    plot_save_path = f"media/plots/{IngredientID}_price_history.png"

    # Plot the price history and save the image
    plot_price_history(ingredient.IngredientName, price_history, plot_save_path)

    # Pass the image file path to the template
    context = {
        'ingredient': ingredient,
        'current_prices': current_prices,
        'plot_image_path': plot_save_path,
        'media_url': settings.MEDIA_URL, 

    }

    # Render the template
    return render(request, 'ingredient_detail.html', context)

def recipe_search(request):
    search_query = request.GET.get('search_query', '')
    recipes = []

    if search_query:
            recipes = Recipe.objects.filter(RecipeName__icontains=search_query).values(
                    'RecipeID',
                    'RecipeName'
            )
    distinct_recipes = {}

    for recipe in recipes:
        recipe_id = recipe['RecipeID']
        if recipe_id not in distinct_recipes:
            distinct_recipes[recipe_id] = recipe

        # Use only the distinct recipes
        recipes = list(distinct_recipes.values())

    return render(request, 'recipe_search.html', {'search_query': search_query, 'recipes': recipes})
    
def shopping_list_detail(request, list_id):
    # Retrieve the shopping list items for the given list ID
    shopping_list_items = ShoppingList.objects.filter(ListID=list_id)

    # Pass the data to the template
    return render(request, 'shopping_list_detail.html', {'shopping_list_items': shopping_list_items})

def recipe_detail(request, RecipeID):
        
    recipe_items = Recipe.objects.filter(RecipeID=RecipeID)
        
    # Pass the data to the template
    return render(request, 'recipe_detail.html', {'recipe_items': recipe_items})