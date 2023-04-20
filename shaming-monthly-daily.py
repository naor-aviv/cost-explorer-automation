import boto3
import datetime
from dateutil.relativedelta import relativedelta
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import json
import os

# Set the date range for the Cost Explorer report - Monthly
start_date = datetime.datetime.today() - relativedelta(months=1)
end_date = datetime.datetime.today() - datetime.timedelta(days=1)

# Convert the dates to strings in the format expected by the billing API - Monthly
start_date_str = start_date.strftime('%Y-%m-%d')
end_date_str = end_date.strftime('%Y-%m-%d')

# set start and end date range (here, we are getting data from yesterday) - Daily
end_date_daily = datetime.datetime.today().strftime('%Y-%m-%d')
start_date_daily = (datetime.datetime.today() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

# Initialize a dictionary to hold the costs for each account
account_costs = {}
account_costs_daily = {}


# Connect to the billing API
ce = boto3.client('ce')

# Get the account IDs for the organization
org = boto3.client('organizations')
accounts = org.list_accounts()

def lambda_handler(event, context):

    total_monthly_cost = 0.0
    total_daily_cost = 0.0

    # Loop through each account and get the costs for the last month
    for account in accounts['Accounts']:
        account_id = account['Id']
        account_name = account['Name']
        
        # Initialize a dictionary to hold the costs for each resource
        resource_costs = {}
        resource_costs_daily = {}
        
    ##  ##  ##  ##  ##  ##  MONTHLY ##  ##  ##  ##  ##  ##  ##  ## 
        
        # Get the costs for each resource in the account for Monthly
        results = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date_str,
                'End': end_date_str
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'LINKED_ACCOUNT'
                },
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ],
            Filter={
                'Dimensions': {
                    'Key': 'LINKED_ACCOUNT',
                    'Values': [account_id]
                }
            }
        )
        
        # Loop through the results and add up the costs for each resource - Monthly
        for result in results['ResultsByTime']:
            for group in result['Groups']:
                service = group['Keys'][1]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])
                if service not in resource_costs:
                    resource_costs[service] =  0.0
                resource_costs[service] += cost
        
        # Add the resource costs for this account to the overall account costs dictionary - MONTHLY
        account_costs[account_id] = {'Name': account_name, 'Total': sum(resource_costs.values()), 'Resources': resource_costs}
        total_monthly_cost += account_costs[account_id]["Total"]
        
        sorted_account_costs = dict(sorted(account_costs.items(), key=lambda x: x[1]['Total'], reverse=True))


    ##  ##  ##  ##  ##  ##  DAILY ##  ##  ##  ##  ##  ##  ##  ## 
    
        # Get the costs for each resource in the account for Daily
        results_daily = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date_daily,
                'End': end_date_daily
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'LINKED_ACCOUNT'
                },
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ],
            Filter={
                'Dimensions': {
                    'Key': 'LINKED_ACCOUNT',
                    'Values': [account_id]
                }
            }
        )

        # Loop through the results and add up the costs for each resource - Daily
        for result_daily in results_daily['ResultsByTime']:
            for group_daily in result_daily['Groups']:
                service_daily = group_daily['Keys'][1]
                cost_daily = float(group_daily['Metrics']['UnblendedCost']['Amount'])
                if service_daily not in resource_costs_daily:
                    resource_costs_daily[service_daily] = 0.0
                resource_costs_daily[service_daily] += cost_daily

        # Add the resource costs for this account to the overall account costs dictionary - DAILY
        account_costs_daily[account_id] = {'Name': account_name, 'Total': sum(resource_costs_daily.values()), 'Resources': resource_costs_daily}
        total_daily_cost += account_costs_daily[account_id]["Total"]

        sorted_account_costs_daily = dict(sorted(account_costs_daily.items(), key=lambda x: x[1]['Total'], reverse=True))


    with open('table.css', 'r') as f:
        css = f.read()
    # Create an HTML table from the account costs
    html_table = f"""
    <html>
    <body>
        <h1>Monthly Cost report</h1>
    <head>
    <style>
    {css}
    </style>
    </head>
    <body>
    <table class="comicGreen">
    <tr>
      <th>Account ID</th>
      <th>Name</th>
      <th>Total Cost</th>
    </tr>
    """
    ####      ###        MONTHLY HTML table     ###       ####
    
    for account_id, account_info in sorted_account_costs.items():
        html_table += f'<tr><td>{account_id}</td><td>{account_info["Name"]}</td><td>{account_info["Total"]:.2f} USD</td></tr>'
    html_table += f'<tr><td></td><td></td><td></td></tr>'
    html_table += f'<tr><td></td><td>Total Organization costs</td><td>{total_monthly_cost:.2f} USD </td></tr>'
    html_table += '</table></body></html>'
    


    ####      ###        DAILY HTML table     ###       ####
    
    # Create an HTML table from the account costs
    html_table_daily = f"""
    <html>
    <body>
        <h1>Daily Cost report</h1>
    <head>
    <style>
    {css}
    </style>
    </head>
    <body>
    <table class="comicGreen">
    <tr>
      <th>Account ID</th>
      <th>Name</th>
      <th>Total Cost</th>
    </tr>
    """

    for account_id, account_info in sorted_account_costs_daily.items():
        html_table_daily += f'<tr><td>{account_id}</td><td>{account_info["Name"]}</td><td>{account_info["Total"]:.2f} USD</td></tr>'
    html_table_daily += f'<tr><td></td><td></td><td></td></tr>'
    html_table_daily += f'<tr><td></td><td>Total Organization costs</td><td>{total_daily_cost:.2f} USD </td></tr>'
    html_table_daily += '</table></body></html>'

    total_table = html_table + html_table_daily
    # Connect to the SES service
    ses = boto3.client('ses')
    
    # Define the email message
    msg = MIMEMultipart()
    msg['Subject'] = 'Monthly & Daily Account Costs'
    msg['From'] = 'naor@terasky.com'
    msg['To'] = 'naor@terasky.com'
    
    # Attach the HTML table as a MIMEText part
    msg.attach(MIMEText(total_table, 'html'))
    
    # Convert the message to a raw string and send it using SES
    raw_msg = msg.as_string()
    ses_response = ses.send_raw_email(
        Source=msg['From'],
        Destinations=[msg['To']],
        RawMessage={'Data': raw_msg}
    )

    # Print the response from SES
    print(ses_response)
