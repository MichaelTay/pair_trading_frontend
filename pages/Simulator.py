import streamlit as st
import time
import numpy as np
import pandas as pd
import json
import pickle
import plotly.express as px
from datetime import datetime as dt
from src.utils import ExecutePairTrading, run_simulation
from streamlit import session_state as ss
import requests
import plotly.graph_objects as go
import os
from st_files_connection import FilesConnection
from PIL import Image
icon = Image.open('images/ppf_logo.png')

# Set the page layout to wide
st.set_page_config(
    layout="wide",
    page_icon=icon
    )

# # Display the custom HTML
# st.components.v1.html(custom_html)
# Set the header
st.markdown("# Parallel Portfolio Simulator")
st.write(
    """
    This Simulator helps you access the performance of our trading system. Tell us the amount of money you are investing and \
    a past date, our simulator will perform the parallel trading strategy and compare the result against SPY.
    """
    )
st.sidebar.image('images/ppf_logo.png')
st.sidebar.header("Parallel Portfolio Simulator")

# Assign sesion state
if 'simulation_ran' not in ss:
    ss['simulation_ran'] = False

ss['check_most_traded_pair'] = False
ss['check_most_profited_pair'] = False
ss['check_least_profited_pair'] = False
ss['check_pair_details'] = False

def convert_str_to_date(x):
    return dt.strptime(x, '%Y-%m-%d').date()

prediction_file = 'data_pipeline_output_multi_entry_pnl_2020onwards_with_predicted_entry_trimmed.csv'
# prediction_file = 'Data/data_pipeline_output_multi_entry_pnl_2020onwards_with_predicted_entry.csv'

@st.cache_data
def load_csv(filepath):
    # Load data
    return pd.read_csv(filepath)

# s3://streamlitbucket-w210-frontend/data_pipeline_output_multi_entry_pnl_2020onwards_with_predicted_entry_trimmed.csv
@st.cache_data
def pull_csv(filepath):
    conn = st.connection('s3', type=FilesConnection)
    transformed_data = conn.read("streamlitbucket-w210-frontend/data_pipeline_output_multi_entry_pnl_2020onwards_with_predicted_entry_trimmed.csv", input_format="csv", ttl=3600)
    transformed_data.to_csv(filepath)
    # transformed_data = pd.read_csv("Data/data_pipeline_output_multi_entry_pnl_2020onwards_with_predicted_entry.csv")
    return transformed_data

def pull_prediction(filepath):
    if not os.path.exists(filepath):
        # Define the URL for the POST request
        url = "http://ec2-13-56-159-9.us-west-1.compute.amazonaws.com:8000/mlapi-predictget"

        # Define the header for the request, specifying the content type
        headers = {
            'Content-Type': 'application/csv',
        }

        # Send the request
        response = requests.get(url, headers=headers)
        # Read as csv
        transformed_data = pd.read_csv(response.content)

        transformed_data.to_csv(filepath)  

file_exists = os.path.exists(prediction_file)
if file_exists:
    transformed_data = load_csv(prediction_file)
else:
    with st.spinner('Loading data...'):
        is_loading = False
        if not file_exists and not is_loading:
          # pull_prediction(prediction_file)
          transformed_data = pull_csv(prediction_file)
          is_loading = True
        while not file_exists:
          # do nothing
          time.sleep(1)
          file_exists = os.path.exists(prediction_file)

total_fund = st.text_input(
    "Starting Funds ($)",
    value=10000
    )

date_column_left, date_column_right, refresh_cadence_input = st.columns(3)
with date_column_left:
    start_date = st.date_input(
        label="Start date",
        value=convert_str_to_date('2022-01-01'),
        min_value=convert_str_to_date(transformed_data.Date.min()),
        max_value=convert_str_to_date(transformed_data.Date.max()),
        help="This is the date when fund where deposited"
        )
with date_column_right:
    end_date = st.date_input(
        label="End date", 
        value=convert_str_to_date('2022-12-31'),
        min_value=convert_str_to_date(transformed_data.Date.min()),
        max_value=convert_str_to_date(transformed_data.Date.max()),
        help='Run simulation till this date'
        )
    
with refresh_cadence_input:
    refresh_cadence = st.text_input(
        label='Refresh Cadence',
        value=60,
        help="""
        This determines how often do you want to close the current positions and refresh the trading strategy;\
        The current models are optimized for 60 trading days
        """
    )

sim_button = st.button("Run Simulation")

st.divider()  # 👈 Draws a horizontal rule
if sim_button:
    # run the simulation
    result, all_execution_history = run_simulation(
        starting_fund=float(total_fund),
        sim_start=str(start_date),
        sim_end = str(end_date),
        transformed_data = transformed_data,
        refresh_cadence = int(refresh_cadence)
    )
    # get the prices of spy
    spy_prices = transformed_data[['Date', 'SPY_Close']].drop_duplicates().reset_index(drop=True)
    spy_prices = spy_prices[
        (spy_prices.Date >= str(start_date)) & (spy_prices.Date <= str(end_date))
    ]
    # merge the tables
    result = pd.merge(spy_prices, result, how='left', on='Date')
    result['spy_return'] = result.SPY_Close.apply(lambda x: float(total_fund)*(x/result.SPY_Close[0]))

    # Clean up the trade execution table
    all_execution_history_cleaned = \
        all_execution_history[
            ['ticker1', 'ticker2', 'entry_dates','exit_dates']
        ].groupby(['ticker1', 'ticker2', 'entry_dates']).max().reset_index()
    
    all_execution_history_cleaned = pd.merge(
        all_execution_history_cleaned,
        all_execution_history[['long_stock_1', 'entry_dates', 'exit_dates', 'ticker1', 'ticker2','pnl']],
        on = ['entry_dates', 'exit_dates', 'ticker1', 'ticker2']
    ).drop_duplicates().reset_index(drop=True)
        
    # Get the latest results
    ss['latest_total_asset'] = round(result.total_asset.values[-1],2)
    ss['delta_pct'] = round((ss['latest_total_asset']/float(total_fund) - 1)*100, 2)
    ss['delta_amount'] = round(ss['latest_total_asset'] - float(total_fund),2)

    ss['num_pair_trading_executed'] = all_execution_history_cleaned.drop_duplicates().shape[0]

    # Update session state
    ss['simulation_ran'] = True
    ss['result'] = result
    ss['all_execution_history_cleaned'] = all_execution_history_cleaned
    ss['start_date'] = start_date
    ss['end_date'] = end_date 


if ss['simulation_ran']:   

    if ss['delta_amount'] >= 0:
        sign = '+'
    else:
        sign = '-'

    # Placeholder for text box, line chart, and table
    mbox_1, mbox_2, mbox_3 = st.columns(3)
    with mbox_1:
        metric_box= st.metric(
            label="Total Assets", 
            value=f"${ss['latest_total_asset']}", 
            delta=f"{ss['delta_amount']}"
        )

    with mbox_2:
        metric_box_2=st.metric(
                    label="Total PnL (%)", 
                    value=f"{sign}{abs(ss['delta_pct'])}%"
                )
    with mbox_3:
        metric_box_3=st.metric(
                    label="Num Pair Trading Strategy Executed", 
                    value=ss['num_pair_trading_executed']
                )

    trend_fig = px.line(
        ss['result'], 
        x="Date", 
        y=['total_asset','spy_return']
        )
    
    # Update the legends
    label_dict = {'total_asset':'Parallel Portfolios', 'spy_return':'S&P 500'}
    trend_fig.for_each_trace(lambda t: t.update(name = label_dict[t.name],
                                        legendgroup = label_dict[t.name],
                                        hovertemplate = t.hovertemplate.replace(t.name, label_dict[t.name])
                                        )
                    )
    
    trend_fig.update_layout(
        yaxis_title='Total Asset ($)',
        title = 'Parallel Portfolio VS SPY 500 Aggregated Return'
    )
    
    st.plotly_chart(
        trend_fig,
        use_container_width=True
    )

    # Get the most traded pair
    temp_df = ss['all_execution_history_cleaned'].groupby(['ticker1','ticker2']).size().sort_values(ascending=False).reset_index()
    ss['most_traded_pair'] = " x ".join([temp_df.head(1).ticker1.values[0],temp_df.head(1).ticker2.values[0]])
    ss['most_traded_pair_count'] = temp_df.shape[0]
    ss['most_traded_ticker1'] = temp_df.ticker1.values[0]
    ss['most_traded_ticker2'] = temp_df.ticker2.values[0]


    # Get the most profited pair
    temp_df = ss['all_execution_history_cleaned'][['ticker1','ticker2','pnl']].groupby(['ticker1','ticker2']).sum().sort_values('pnl',ascending=False).reset_index()
    ss['most_profited_pair'] = " x ".join([temp_df.head(1).ticker1.values[0],temp_df.head(1).ticker2.values[0]])
    ss['most_profited_pair_profit'] = round(temp_df.head(1).pnl.values[0],2)
    ss['most_profit_ticker1']=temp_df.head(1).ticker1.values[0]
    ss['most_profit_ticker2']=temp_df.head(1).ticker2.values[0]


    # get the least profited pair
    ss['least_profited_pair'] = " x ".join([temp_df.tail(1).ticker1.values[0],temp_df.tail(1).ticker2.values[0]])
    ss['least_profited_pair_profit'] = round(temp_df.tail(1).pnl.values[0], 2)
    ss['least_profit_ticker1'] = temp_df.tail(1).ticker1.values[0]
    ss['least_profit_ticker2'] = temp_df.tail(1).ticker2.values[0]

    mbox_4, mbox_5, mbox_6 = st.columns(3)
    with mbox_4:
        metric_box= st.metric(
            label="Most Traded Pair", 
            value=f"{ss['most_traded_pair']}"
        )
        ss['check_most_traded_pair'] = st.button('Examine Most Traded Pair')

    with mbox_5:
        metric_box_2=st.metric(
                    label="Most Profited Pair", 
                    value=f"{ss['most_profited_pair']}", 
                    delta=ss['most_profited_pair_profit']
                )
        ss['check_most_profited_pair'] = st.button('Examine Most Profited Pair')

    with mbox_6:
        metric_box_3=st.metric(
                    label="Least Profited Pair", 
                    value=f"{ss['least_profited_pair']}", 
                    delta=ss['least_profited_pair_profit']
                )
        ss['check_least_profited_pair'] = st.button('Examine Most Lost Pair')

if ss['check_most_traded_pair']:
    ss['target_ticker1'] = ss['most_traded_ticker1']
    ss['target_ticker2'] = ss['most_traded_ticker2']
    ss['check_pair_details'] = True

if ss['check_most_profited_pair']:
    ss['target_ticker1'] = ss['most_profit_ticker1']
    ss['target_ticker2'] = ss['most_profit_ticker2']
    ss['check_pair_details'] = True

if ss['check_least_profited_pair']:
    ss['target_ticker1'] = ss['least_profit_ticker1']
    ss['target_ticker2'] = ss['least_profit_ticker2']
    ss['check_pair_details'] = True

if ss['check_pair_details']:
    # Filter the execution record to specific pairs
    specific_pairs = ss['all_execution_history_cleaned'][
        (ss['all_execution_history_cleaned'].ticker1==ss['target_ticker1']) &
        (ss['all_execution_history_cleaned'].ticker2==ss['target_ticker2'])
    ]

    # Re-construct the execution history tables
    ticker1_history = specific_pairs[['ticker1','entry_dates','exit_dates','long_stock_1']]
    ticker1_history_entry = ticker1_history[['ticker1','entry_dates','long_stock_1']]
    ticker1_history_entry.columns = ['ticker','execution_date','long']

    ticker1_history_exit = ticker1_history[['ticker1','exit_dates','long_stock_1']]
    ticker1_history_exit.columns = ['ticker','execution_date','long']
    # execute reverse action to exit
    ticker1_history_exit['long'] = -ticker1_history_exit['long']
    ticker1_history = pd.concat([
        ticker1_history_entry,
        ticker1_history_exit
    ]).reset_index(drop=True)

    ticker2_history = specific_pairs[['ticker2','entry_dates','exit_dates','long_stock_1']]
    ticker2_history_entry = ticker2_history[['ticker2','entry_dates','long_stock_1']]
    ticker2_history_entry.columns = ['ticker','execution_date','long']
    # longing ticker 1 means shorting ticker 2
    ticker2_history_entry['long'] = -ticker2_history_entry['long']

    ticker2_history_exit = ticker2_history[['ticker2','exit_dates','long_stock_1']]
    ticker2_history_exit.columns = ['ticker','execution_date','long']

    ticker2_history = pd.concat([
        ticker2_history_entry,
        ticker2_history_exit
    ]).reset_index(drop=True)

    ticker_history_combined = pd.concat([
        ticker1_history,
        ticker2_history
    ]).reset_index(drop=True)

    # get price history
    target_ticker1_price_hist = transformed_data[
        (transformed_data.Ticker_P1==ss['target_ticker1'])
    ][['Date','Close_P1']].drop_duplicates()

    target_ticker1_price_hist.columns = ['Date',ss['target_ticker1']]

    target_ticker2_price_hist = transformed_data[
        (transformed_data.Ticker_P2==ss['target_ticker2'])
    ][['Date','Close_P2']].drop_duplicates()

    target_ticker2_price_hist.columns = ['Date',ss['target_ticker2']]

    target_ticker_price_hist = pd.merge(
        target_ticker1_price_hist,
        target_ticker2_price_hist,
        how='inner',
        on='Date'
    )

    # Filter to the date of simulation
    target_ticker_price_hist = target_ticker_price_hist[
        (target_ticker_price_hist.Date >= str(start_date)) 
        # & ((target_ticker_price_hist.Date <= str(end_date)))
    ].reset_index(drop=True)

    ticker_price_fig = px.line(
        target_ticker_price_hist, 
        x="Date", 
        y=[ss['target_ticker1'],ss['target_ticker2']]
        )

    # Bring in the price info
    price_on_execution = []
    for idx in ticker_history_combined.index:
        temp_ticker = ticker_history_combined.loc[idx]['ticker']
        temp_date = ticker_history_combined.loc[idx]['execution_date']
        price_on_execution.append(
            target_ticker_price_hist[
                (target_ticker_price_hist.Date==temp_date)
            ][temp_ticker].values[0]
        )
    ticker_history_combined['price_on_execution']=price_on_execution

    # Add the buy
    ticker_price_fig.add_traces(
        go.Scatter(
            x=ticker_history_combined['execution_date'][ticker_history_combined.long], 
            y=ticker_history_combined['price_on_execution'][ticker_history_combined.long], 
            mode="markers",
            marker_color='green',
            marker_symbol='triangle-up',
            marker_size=10,
            name='Buy'
        )
    )

    # Add the sell
    ticker_price_fig.add_traces(
        go.Scatter(
            x=ticker_history_combined['execution_date'][ticker_history_combined.long==False], 
            y=ticker_history_combined['price_on_execution'][ticker_history_combined.long==False], 
            mode="markers",
            marker_color='red',
            marker_symbol='triangle-down',
            marker_size=10,
            name='Sell'
        )
    )

    # update the chart range
    ticker_price_fig.update_layout(
        xaxis_range = [start_date, end_date],
        yaxis_title = 'Price($)'
    )

    st.plotly_chart(ticker_price_fig, use_container_width=True)
