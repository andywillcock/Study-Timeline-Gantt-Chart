import pandas as pd
import re
from datetime import date, datetime
from wx import App, FileSelector, GetTextFromUser
import plotly
import plotly.figure_factory as plyff

def strip_date(gantt_df):
    """
    Converts start and end dates in gantt formatted data frame to datetimes.

    :param gantt_df: data frame with Start Date and Completion Columns
    :return: gantt_df: data frame with string dates converted to datetimes.
    """
    for col in ['Start Date', 'Completion Date']:
        for row in range(len(gantt_df)):
            gantt_df[col][row] = pd.to_datetime(gantt_df[col][row], errors = 'coerce')

    return gantt_df
def remove_nonascii(gantt_df):
    for col in list(gantt_df.columns.get_values()):
        if gantt_df[col].dtype not in ['float64', 'int64', 'datetime64[ns]']:
            gantt_df[col].replace({r'[^\x00-\x7F]+': ''}, regex=True, inplace=True)
    return gantt_df

def extract_NCT(gantt_df):
    """
    Extracts NCT numbers from a data frame with mulitple types of study identifiers in the same cell.
    :param gantt_df: data formatted from merged CT.gov and TA Scan data tables
    :return: gantt_df: gantt_df with NCT Identifier column added
    """
    nct = r'\b(NCT\w+)\b'
    NCT_numbers = []
    for a in range(len(gantt_df)):
        ident = str(gantt_df['Alternative IDs'][a]).split(',')
        ident = re.findall(nct,' '.join(ident))
        if len(ident) > 0:
            ident = ident[0]
        else:
            ident = 'No NCT Identifier'
        NCT_numbers.append(ident)
    ncts = pd.Series(NCT_numbers)
    gantt_df['NCT Number'] = ncts
    return gantt_df

app = App()
ta_file = FileSelector("Please select a TA-Scan Export Saved as an .xlsx file",default_extension='.xlsx')
ctgov_file = FileSelector("Please select a clinicaltrials.gov Export Saved as an .csv file",default_extension='.csv')

# Read in TA Scan data and format keeping only necessary columns to merge with the CT.gov data
ta_df = pd.read_excel(ta_file, header=0)
ta_df = remove_nonascii(ta_df)
ta_df = extract_NCT(ta_df)
ta_df = ta_df[ta_df['NCT Number'] != 'No NCT Identifier']
ta_df = ta_df[['NCT Number','Enrollment', 'Nr sites', 'Study start', 'Study end']].reset_index(level=0, drop=True)
ta_df.columns = ['NCT Number','Enrollment', 'Num. of Sites', 'Start Date', 'Completion Date']
ta_df=remove_nonascii(ta_df)
ta_df.to_csv('./ta_scan.csv', index=False)
ta_df = strip_date(ta_df)

# Read in CT.gov data and format to keep only necessary columns for merging with the TA Scan data
ct_df = pd.read_csv(ctgov_file, header=0)
ct_df = ct_df.drop('Rank', axis = 1)
ct_df = ct_df[list(ct_df.columns.get_values()[0:9])]
col_names = list(ct_df.columns.get_values())
ct_df = remove_nonascii(ct_df)
ct_df = strip_date(ct_df)

# Merge CT.gov Data with the TA Scan data combining matching studies
all_data = pd.merge(ta_df, ct_df, how='outer', on='NCT Number',suffixes=('_ta','_ct'))

# Convert dates in merged data frame from %m/%d/%Y hh:mm:ss format to %m/%d/%Y format
for date_col in ['Start Date_ta', 'Completion Date_ta', 'Start Date_ct', 'Completion Date_ct']:
    all_data[date_col] = pd.to_datetime(all_data[date_col],format='%m/%d/%Y')
    all_data[date_col] = all_data[date_col].apply(lambda x: x.date())

# Replace missing dates in Enrollment, Start, and Completion date columns from TA Scan with the data from CT.gov table
for row in range(len(all_data)):
    if pd.isna(all_data['Start Date_ta'][row]) == True:
        all_data['Start Date_ta'][row] = all_data['Start Date_ct'][row]
    if pd.isna(all_data['Completion Date_ta'][row]) == True:
        all_data['Completion Date_ta'][row] = all_data['Completion Date_ct'][row]
    if pd.isna(all_data['Enrollment_ta'][row]) == True:
        all_data['Enrollment_ta'][row] = all_data['Enrollment_ct'][row]

# Remove columns that are not necessary for Gantt Chart creation
all_data = all_data.drop(['Title','Status','Study Results','Conditions', 'Phases', 'Enrollment_ct',
                          'Start Date_ct', 'Completion Date_ct'], axis=1)
all_data.columns = ['NCT Number', 'Enrollment', 'Num. of Sites', 'Start Date', 'Completion Date']

# Remove any rows containing NaN for either Start or End Date as they can't be graphed correctly
all_data = all_data[pd.isna(all_data['Start Date'])==False]
all_data = all_data[pd.isna(all_data['Completion Date'])==False]

# Take lower limit for dates studies were started from user
low_date = GetTextFromUser(message = "Enter the Lower Limit year for the time period of interest",
                           caption = "Lower Limit of Time Period",
                           default_value=str(datetime.now().year))

# Convert Enrollment and Number of Sites to integers
all_data['Enrollment'] = all_data['Enrollment'].astype(int, errors='ignore')
all_data['Num. of Sites'] = all_data['Num. of Sites'].astype(int,  errors='ignore')

# Subset data based on the lower date limit submitted by the user
all_data = all_data[all_data['Start Date'] >= date(int(low_date), 1, 1)].reset_index(level=0,drop=True)

# Save  all_data df as .csv file to the working directory
all_data.to_csv('./all_data.csv', index=False)


################# Creation of Gantt Chart using Plotly #################

#  Extract data for gantt graph from all_data table
gantt_graph_data = all_data[['NCT Number','Start Date', 'Completion Date']]
label_data = all_data

#Rename columns to work with plotly's pandas integration
gantt_graph_data.columns = ['Task','Start','Finish']

# Create gantt graph object
fig = plyff.create_gantt(gantt_graph_data,colors = '#4682b4', show_colorbar=True,bar_width=0.2, showgrid_x=True,
                         showgrid_y=True)

# Format plot area to fit plot and put x-axis with years on the top of the chart area
fig['layout'].update(autosize=True, width=2000, height=1000, margin=dict(l=400),
                     yaxis=dict(autorange=True, showgrid=False, zeroline=False, showline=False, autotick=True,ticks='',
                                showticklabels=False),
                     xaxis = dict(side='top',range=[min(label_data['Start Date'])-pd.to_timedelta(1,unit='Y'),
                                                    max(label_data['Completion Date']) + pd.to_timedelta(1, unit='Y')]))

# Create annotations for each timeline bar with Phase, NCT Number, and Enrollment and Number of Sites if available
for i in range(len(fig["data"])):
    if pd.isna(label_data['Num. of Sites'][i]) or pd.isna(label_data['Enrollment'][i]):
        fig["data"][i].update(
            text=["Ph 3 " + label_data["NCT Number"][i]],
            mode="markers+text",
            textposition="top left",
            textfont=dict(size=8))
    else:
        fig["data"][i].update(
            text=["Ph 3 " + label_data["NCT Number"][i] + " ("+str(int(label_data['Enrollment'][i]))+ " subj, " +
                 str(int(label_data['Num. of Sites'][i]))+ " sites)"],
            mode="markers+text",
            textposition = "top left",
            textfont=dict(size=8))

# Save graph as html file
plotly.offline.plot(fig, filename='gantt-graph.html')