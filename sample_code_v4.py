import pandas as pd
import numpy as np
import pymysql
import random
import os
import pickle
from datetime import timedelta
import random
import warnings
warnings.filterwarnings('ignore')

# db login
db = pymysql.connect(host='', port=, user='', passwd='', db='', charset='')
cur = db.cursor()

# table pickle file 
operations_pickle_file = 'operations.pickle'
labevents_pickle_file = 'labevents.pickle'
diagnosis_pickle_file = 'diagnosis.pickle'
vitals_pickle_file = 'vitals.pickle'
ward_vitals_pickle_file = 'ward_vitals.pickle'

# parameter file
vitals_parid_file = 'vital_parid_list.xlsx'
labs_parid_file = 'lab_parid_list.xlsx'
icd9_to_icd10_file = 'icd9toicd10pcs.csv'

# deidentified mapping file
opid_mapping_file = 'opid_mapping.csv'
hid_mapping_file = 'hid_mapping.csv'
hadm_mapping_file = 'hadm_mapping.csv'

# dtstart, dtend based on opdate
DTSTART = '2011-01-01'
DTEND = '2020-12-31'

# opid made by DTSTART, DTEND
dtstart =  int(DTSTART[2:].replace('-',''))*1000
dtend = int(DTEND[2:].replace('-',''))*1000 + 1000

# make lab parameters dictionary
def make_lab_dictionary():
    dflcode = pd.read_excel(labs_parid_file, usecols=['lab name', '정규랩', 'POCT'])
    dflcode = dflcode.dropna(subset=['정규랩','POCT'], how='all', axis=0).fillna('') # lab code가 없는 검사는 제외
    dflcode['parid'] = dflcode[['정규랩','POCT']].apply(lambda row: ', '.join(row.values.astype(str)), axis=1)

    dictlcode = dict()
    for col in dflcode[['lab name', 'parid']].values: 
        name = col[0]
        ids = col[1].split(', ')
        
        for id in ids:
            if id == '':
                continue
            dictlcode[int(id)]=name
        
    return dictlcode

# make vital parameters dictionary
def make_vital_dictionary():
    dfvcode = pd.read_excel(vitals_parid_file).dropna(subset=['inspire'], axis=0)
    return dict(dfvcode[['parid','inspire']].values)

# replace icd9 to icd10
def icd9_to_icd10_code():
    dficd = pd.read_csv(icd9_to_icd10_file).astype(str)
    dficd['icd10code'] = dficd['icd10cm'] ############
    
    # for approach column  
    dficd.loc[(dficd['icd10cm'].str[4]=='4')|(dficd['icd10cm'].str[4]=='5')|(dficd['icd10cm'].str[4]=='7')|(dficd['icd10cm'].str[4]=='8'), 'videoscopic'] = 1
    dficd.loc[dficd['icd10cm'].str[4]=='0', 'videoscopic'] = 0
    
    # for icd10_pcs column
    dficd['icd10cm'] = dficd['icd10cm'].str[:4]
    dficd.loc[dficd['icd10cm']=='NoPC', 'icd10cm'] = ''
    
    dictapproach = dict(dficd.drop_duplicates(subset='icd9cm')[['icd9cm','videoscopic']].values) 
    dicticd = dict(dficd.drop_duplicates(subset='icd9cm')[['icd9cm','icd10cm']].values) 
    dicttest = dict(dficd.drop_duplicates(subset='icd9cm')[['icd9cm','icd10code']].values) #############
    
    return dicticd, dictapproach, dicttest ###########

# replace anetype name
def replace_anetype(ane):
    if ane == 'General':
        return 'General'
    elif ane == 'Spinal':
        return 'Spinal'
    elif ane == 'Epidural':
        return 'Epidural'
    elif ane == 'Combined (S,E)':
        return 'Combined'
    elif ane == 'MAC':
        return 'MAC'
    else:
        return ''

# replace float to int
def replace_int(row):
    try:
        return(int(row))
    except:
        return(0)

# if the data is within the check-in time, 1
def extract_wanted_period(admission_date, recorddate, discharge_date):
    if (admission_date<=recorddate) & (recorddate<=discharge_date):
        return 1
    else:
        return 0   

# convert to relative time based on orin
def convert_to_relative_time(orin, dt):
    total_minutes = (dt-orin).total_seconds() / 60
    if np.isnan(total_minutes):
        return ''
    else:
        return round(total_minutes/5)*5

# labeling to remove non-real numbers
def extract_float(x):
    try: 
       x = float(x)
       return 1
    except:
        return 0 
    
# deidentified data
def deidentified_data(df):
    print('start de identifying...', end='')
    # 1. de-opid made by opid and mapping list
    mapping_opid_df = pd.read_csv(opid_mapping_file, dtype={'opid':float})
    mapping_opid_dict = dict(mapping_opid_df.values)
    df['opid'] = df['opid'].map(mapping_opid_dict).astype(int)
    
    # 2. de-subject_id made by subject_id and mapping list
    print('subject_id...', end='')
    if 'subject_id' in df.columns: 
        try:
            mapping_hid_df = pd.read_csv(hid_mapping_file) 
            mapping_hid_dict = dict(mapping_hid_df.values)
        except:
            mapping_hid_df = dict()
        
        # give de-id only to values not in mapping list
        for hid in list(set(df['subject_id'])-set(mapping_hid_dict.keys())):
            dehid = random.randint(1, 10**8) + 1*10**8
            # must not be the same as the existing de-id
            while dehid in mapping_hid_dict.values(): 
                dehid = random.randint(1, 10**8) + 1*10**8
                if dehid not in mapping_hid_dict.values():
                    mapping_hid_dict[hid] = dehid
                    break
            else: 
                mapping_hid_dict[hid] = dehid
        
        df['dehid'] = df['subject_id'].map(mapping_hid_dict)
        
        # save mapping list as csv
        mapping_hid_df = pd.DataFrame.from_dict(mapping_hid_dict, orient='index').reset_index()
        mapping_hid_df.columns = ['hid', 'dehid']
        mapping_hid_df.to_csv(hid_mapping_file, index=False)
    
    # 3. hadm_id made by subject_id and admissiontime and mapping list
    print('hadm_id...', end='')
    df['hid_adm'] = df['subject_id'].astype(str) + ' ' + df['admissiontime'].astype(str)
    if 'hadm_id' in df.columns:
        try: 
            mapping_hadm_df = pd.read_csv(hadm_mapping_file)
            mapping_hadm_dict = dict(mapping_hadm_df.values)
        except:
            mapping_hadm_dict = dict()
        
        # give de-id only to values not in mapping list
        for hid_adm in set((df['hid_adm']).drop_duplicates().values) - set(mapping_hadm_dict.keys()):
            deadm = random.randint(1, 10**8) + 2*10**8
            # must not be the same as the existing de-id
            while deadm in mapping_hadm_dict.values():
                deadm = random.randint(1, 10**8) + 2*10**8
                if deadm not in mapping_hadm_dict.values():
                    mapping_hadm_dict[hid_adm] = deadm
                    break
            else:
                mapping_hadm_dict[hid_adm] = deadm
                
        df['hadm_id'] = df['hid_adm'].map(mapping_hadm_dict)
        
        # save mapping list as csv
        mapping_hadm_df = pd.DataFrame.from_dict(mapping_hadm_dict, orient='index').reset_index()
        mapping_hadm_df.columns = ['hid_adm', 'hadm_id']
        mapping_hadm_df.to_csv(hadm_mapping_file, index=False) 

    # change column name from 'dehid' to 'subject_id' after creating hadm
    if 'dehid' in df.columns:
        df['subject_id'] = df['dehid']
        
    print('done')
    return df

# make operations table
def make_operations_table(dtstart, dtend):
    col_list = ['opid', 'subject_id', 'orin', 'outtime', 'anstarttime', 'anendtime', 'opstarttime', 'opendtime', 'admissiontime', 'dischargetime', 'deathtime_inhosp', 'opname', 'age', 'gender', 'height', 'weight', 'asa', 'emop', 'department', 'icd10_pcs', 'anetype', 'caseid']

    # ROUND(age,-1)
    sql = f'SELECT opid, hid, orin, orout, aneinfo_anstart, aneinfo_anend, opstart, opend, admission_date, discharge_date, death_time, opname, ROUND(age) , sex, ROUND(height), ROUND(weight), premedi_asa, em_yn, dept, replace(icd9_cm_code, ".", ""), aneinfo_anetype, caseid FROM operations WHERE opid > {dtstart} and opid < {dtend} and age >= 18 and age <= 90 and anetype != "국소" and orin IS NOT NULL and orout IS NOT NULL and admission_date IS NOT NULL and discharge_date IS NOT NULL and grp = "OR"'

    cur.execute(sql)
    dfor = pd.DataFrame(cur.fetchall(), columns=col_list).fillna('')
    dfor = dfor.astype({'admissiontime':'datetime64[ns]',
                        'dischargetime':'datetime64[ns]',
                        'anstarttime':'datetime64[ns]',
                        'anendtime':'datetime64[ns]',
                        'opstarttime':'datetime64[ns]',
                        'opendtime':'datetime64[ns]',
                        'deathtime_inhosp':'datetime64[ns]'
                        })
    
    # add column : hadm_hid
    dfor['hadm_id'] = '' 
    
    # add approach column
    dicticd, dictapproach, dicttest = icd9_to_icd10_code()
    dfor['videoscopic'] = dfor['icd10_pcs'].map(dictapproach)
    dfor.loc[(dfor['videoscopic']=='0') & (dfor['opname'].str.contains('laparosco|robotic|hysterosco|endosco', na=False, case=False)), 'videoscopic'] = 1
    # dfor['videoscopic'].fillna(0, inplace=True)
    dfor['icd_10_code'] = dfor['icd10_pcs'].map(dicttest)
    
    # replace 9 with 10 code
    dfor['icd10_pcs'] = dfor['icd10_pcs'].map(dicticd)
    
    # replace anetype title
    dfor['anetype'] = dfor.apply(lambda x: replace_anetype(x['anetype']), axis=1)
    
    # convert real numbers to integer
    dfor['age'] = dfor.apply(lambda x : replace_int(x['age']), axis=1)
    dfor['height'] = dfor.apply(lambda x : replace_int(x['height']), axis=1)
    dfor['weight'] = dfor.apply(lambda x : replace_int(x['weight']), axis=1)
    
    # replace emop column
    dfor.loc[dfor['emop']=='Y', 'emop'] = 1
    dfor.loc[(dfor['emop']=='N')|(dfor['emop']=='정'), 'emop'] = 0
    
    dfor.to_csv('age_수정2.csv', index=False, encoding='utf-8-sig')
    
    return dfor

# make labevents table
def make_labevents_table(dfor):
    cur = db.cursor()
    sql = f'SELECT * FROM labs WHERE dt >= DATE_SUB("{DTSTART}", INTERVAL 1 MONTH) and dt <= DATE_ADD("{DTEND}", INTERVAL 1 MONTH)'
    cur.execute(sql)
    data = cur.fetchall()
    
    col_list = ['row_id', 'subject_id', 'itemname', 'charttime', 'value']
    dflab = pd.DataFrame(data, columns=col_list)
    
    dictlcode = make_lab_dictionary()
    dflab.replace({'itemname': dictlcode}, inplace=True)
    dflab = dflab[dflab['itemname'].str.contains('|'.join(list(set(dictlcode.values()))), na=False)] # remove all lab not in the lab dictionary
    
    # remove all not real values
    dflab['float'] = dflab['value'].apply(extract_float)
    dflab = dflab[dflab['float']==1] 
    
    dfmerge = pd.merge(dflab, dfor[['opid', 'orin', 'subject_id', 'admissiontime','dischargetime']], how='left', on = 'subject_id')
    dfmerge['dcnote'] = dfmerge.apply(lambda x: extract_wanted_period(x['orin']-timedelta(days=30), x['charttime'], x['orin']+timedelta(days=30)), axis=1) # only lab data within 1 month from orin
    dfresult = dfmerge[dfmerge.dcnote == 1]
    dfresult['charttime'] = dfresult.apply(lambda x: convert_to_relative_time(x['orin'], x['charttime']), axis=1) # relative time based on orin
    dfresult.drop(['admissiontime','dischargetime', 'dcnote', 'orin', 'float'], axis=1, inplace=True)    
        
    return dfresult

# make vitals table
def make_vitals_table(dfor, dtstart, dtend):
    cur = db.cursor()
    sql = f'SELECT * FROM vitals WHERE opid > {dtstart} and opid < {dtend}'
    cur.execute(sql)
    data = cur.fetchall()
    
    col_list = ['opid', 'itemname', 'charttime', 'value', 'row_id']
    dfvital = pd.DataFrame(data, columns=col_list)
    
    # remove all value not in the vital dictionary
    dictvcode = make_vital_dictionary()
    dfvital.replace({'itemname': dictvcode}, inplace=True)
    dfvital = dfvital[dfvital['itemname'].str.contains('|'.join(list(set(dictvcode.values()))), na=False)]
    
    # remove non-real numbers
    dfvital['float'] = dfvital['value'].apply(extract_float)
    dfvital = dfvital[dfvital['float']==1]
    
    # replace relative time based on orin
    dfmerge = pd.merge(dfvital, dfor[['opid', 'orin']], how='left', on = 'opid')
    dfmerge['charttime'] = dfmerge.apply(lambda x: convert_to_relative_time(x['orin'], x['charttime']), axis=1)

    dfmerge.drop(['row_id', 'orin', 'float'], axis=1, inplace=True)
    
    return dfmerge

# make ward vitals table
def make_ward_vitals_table(dfor):
    listhid = list(dfor['subject_id'].unique())
    
    n = 100
    listhids = [listhid[i * n:(i + 1) * n] for i in range((len(listhid) - 1 + n) // n )]
    
    dfwvital = pd.DataFrame(columns=['row_id', 'subject_id', 'itemname', 'charttime', 'value'])
    for hids in listhids:
        cur = db.cursor()
        sql = f'SELECT * FROM ward_vitals WHERE hid IN {tuple(hids)}'
        cur.execute(sql)
        data = cur.fetchall()
        
        datawvital = pd.DataFrame(data)
        dfwvital = dfwvital.append(datawvital, ignore_index=True)
        print(len(dfwvital))
        
    # remove all value not in the vital dictionary
    dictvcode = make_vital_dictionary()
    dfwvital.replace({'itemname': dictvcode}, inplace=True)
    dfwvital = dfwvital[dfwvital['itemname'].str.contains('|'.join(list(set(dictvcode.values()))), na=False)]
    
    dfwvital['float'] = dfwvital['value'].apply(extract_float) 
    dfwvital = dfwvital[dfwvital['float']==1] # remove all not real values
    
    # only ward vital data within admission time and discharge time
    dfmerge = pd.merge(dfwvital, dfor[['opid', 'orin', 'subject_id', 'admissiontime','dischargetime']], how='left', on = 'subject_id')
    dfmerge['dcnote'] = dfmerge.apply(lambda x: extract_wanted_period(x['admissiontime'], x['charttime'], x['dischargetime']), axis=1) 
    dfresult = dfmerge[dfmerge.dcnote == 1]
    
    # replace relative time based on orin
    dfresult['charttime'] = dfresult.apply(lambda x: convert_to_relative_time(x['orin'], x['charttime']), axis=1)
    
    dfresult.drop(['row_id', 'subject_id', 'admissiontime', 'dischargetime', 'dcnote', 'orin', 'float'], axis=1, inplace=True) 
    
    return dfresult

# make diagnosis table
def make_diagnosis_table(dfor):
    dfdgn = pd.read_csv('dataset_diagnosis_total.csv.xz', parse_dates=['진단일자']) # from supreme data
    dfdgn = dfdgn[['환자번호','진단일자','ICD10코드']].drop_duplicates()
    dfdgn.columns = ['subject_id', 'charttime', 'icd_code']
    
    # icd code is up to the first 3 letters only
    dfdgn['icd_code'] = dfdgn['icd_code'].str[:3]

    # only diagnosis data within admission time and discharge time
    dfmerge = pd.merge(dfdgn, dfor[['opid', 'orin', 'subject_id', 'admissiontime','dischargetime']], how='left', on = 'subject_id') 
    dfmerge['dcnote'] = dfmerge.apply(lambda x: extract_wanted_period(x['admissiontime'], x['charttime'], x['dischargetime']), axis=1) 
    dfresult = dfmerge[dfmerge.dcnote == 1]
    
    # replace relative time based on orin
    dfresult['charttime'] = dfresult.apply(lambda x: convert_to_relative_time(x['orin'], x['charttime']), axis=1)

    dfresult.drop(['orin', 'admissiontime','dischargetime', 'dcnote'], axis=1, inplace=True)    
        
    return dfresult

# make vital table labeling
def make_vital_labeling(dfor):
    print('start vital labeling...cpb...', end='')
    # 1. cpb on/off
    dfcpb = pd.read_excel('cpb_time_data.xlsx', usecols= ['환자번호','서식작성일','진료서식구성원소ID','서식내용'], skiprows=1, parse_dates=['서식작성일'])
    
    # the largest time value is cpb off, the smallest time value is cpb on
    cpbmax = dfcpb.groupby(['환자번호','서식작성일'], as_index=False)['진료서식구성원소ID'].max() 
    cpbmin = dfcpb.groupby(['환자번호','서식작성일'], as_index=False)['진료서식구성원소ID'].min() 

    dfmax = pd.merge(cpbmax, dfcpb, on = ['환자번호','서식작성일','진료서식구성원소ID']) 
    dfmin = pd.merge(cpbmin, dfcpb, on = ['환자번호','서식작성일','진료서식구성원소ID']) 
    
    dfmax['서식항목명'] = 'cpb off'
    dfmin['서식항목명'] = 'cpb on'
    
    # search when the record of OR using by '서식작성일'
    dfcpb = dfmax.append(dfmin, ignore_index=True).sort_values(['서식작성일'])
    operations_df['opdate'] = operations_df['orin'].dt.date
    cpbopid = pd.merge(dfcpb, operations_df[['opid','subject_id','opdate','orin']], how='left',  left_on=['환자번호','dt'], right_on=['subject_id','opdate'])
    cpbopid = cpbopid[cpbopid['opdate'].notnull()] # if not included in dtsart and dtend, should be removed because of null value
    cpbopid['서식내용'] = cpbopid['서식내용'].replace('/', ':', regex=True).replace('24:', '0:', regex=True) # fix typos
    
    # cpb on/off time search for each operation case
    cpb_dfresult = pd.DataFrame(columns=['opid','charttime','itemname','value'])
    for col in cpbopid[['opid','orin']].drop_duplicates().values:
        dicttime = dict()
        opid = col[0]
        orin = col[1]
        
        data = cpbopid[cpbopid['opid']==opid]
        
        # assume 'the date in cpb time' == 'orin'
        data['dt'] = pd.to_datetime(data['orin'].dt.date.astype(str)  + ' ' + data['서식내용'])
        dicttime['orin'] = orin
        
        dicttime.update(dict(data[['서식항목명','dt']].values))
        
        # if cpb time < orin, change 'the date in cpb time'
        if dicttime['cpb on'] < dicttime['orin']:
            dicttime['cpb on'] = dicttime['cpb on'] + timedelta(days=1)
        if dicttime['cpb off'] < dicttime['orin']:
            dicttime['cpb off'] = dicttime['cpb off'] + timedelta(days=1)
        
        dftime = pd.DataFrame.from_records([dicttime], index=['time'])
        
        # ??? 이 순서 괜찮나?
        dftime['cpb on'] = dftime.apply(lambda x: convert_to_relative_time(x['orin'], x['cpb on']), axis=1)
        dftime['cpb off'] = dftime.apply(lambda x: convert_to_relative_time(x['orin'], x['cpb off']), axis=1)
        
        # labeling all times between cpb on and cpb off as 1 in 5 minute intervals
        result = pd.DataFrame(range(dftime['cpb on'].values[0], dftime['cpb off'].values[0]+1,5), columns=['charttime']) 
        result[['opid', 'itemname', 'value']] = [opid, 'cpb', 1]
        cpb_dfresult = cpb_dfresult.append(result, ignore_index=True)
        print(cpb_dfresult)        
    
    # 2. crrt, ecmo
    # sql = SELECT icuid, icuroom, hid, icuin, icuout FROM `admissions` WHERE icuout > '2011-01-01' and icuin < '2020-12-31'
    print('ecmo...crrt...', end='')
    dfce = pd.read_excel('ecmo_crrt_2020_sample_data.xlsx', skiprows=1, usecols=['환자번호','[간호기록]기록작성일시','Entity','Value'], parse_dates=['[간호기록]기록작성일시'])
    dfce.columns= ['subject_id','charttime','entity','value']
    dfce.loc[dfce['entity']=='혈액투석', 'entity'] = 'crrt'
    dfce.loc[dfce['entity']=='Extracorporeal Membrane Oxygenator', 'entity'] = 'ecmo'
    
    dfmerge = pd.merge(dfce, dfor[['opid', 'orin', 'outtime', 'subject_id', 'dischargetime']], how='left', on = 'subject_id')
    dfmerge = dfmerge[dfmerge['opid'].notnull()] # if not included in dtsart and dtend, should be removed because of null value
    
    # only ecmo, crrt data within or outtime and discharge time
    dfmerge['dcnote'] = dfmerge.apply(lambda x: extract_wanted_period(x['outtime'], x['charttime'], x['dischargetime']), axis=1) 
    dfmerge = dfmerge[dfmerge.dcnote == 1]
    dfmerge['charttime'] = dfmerge.apply(lambda x: convert_to_relative_time(x['orin'], x['charttime']), axis=1)
    
    # crrt, ecmo time search for each operation case and entity
    ecmo_crrt_dfresult = pd.DataFrame(columns=['opid','charttime','itemname','value'])
    for col in dfmerge[['opid','entity']].drop_duplicates().values: 
        opid = col[0]
        entity = col[1]
        
        # the maximum interval for crrt is 8 hours, the maximum interval for ecmo is 4 hours
        data = dfmerge[(dfmerge['opid']==opid) & (dfmerge['entity']==entity)].reset_index(drop=True)
        if entity == 'crrt':
            idxes = list(data[data.charttime.diff(periods=-1) < -60*8].index) 
        elif entity == 'ecmo':
            idxes = list(data[data.charttime.diff(periods=-1) < -60*4].index)
        idxes.insert(0,-1)
        idxes.append(data.index.max())
        
        # search for idxes with a maximum interval lager than 8 hours and label all intermittent hours in those idxes as 1
        for idx in range(len(idxes)-1): 
            result = pd.DataFrame(range(data.iloc[idxes[idx]+1]['charttime'], data.iloc[idxes[idx+1]]['charttime']+1, 5), columns=['charttime'])
            result[['opid', 'itemname', 'value']] = [opid, entity, 1]
            ecmo_crrt_dfresult = ecmo_crrt_dfresult.append(result, ignore_index=False)
            
    # 3. mv
    print('mv...', end='')
    dfmvgcs = pd.read_excel('mv_gcs_2020_sample_data.xlsx', skiprows=1, usecols=['환자번호','[간호기록]기록작성일시','Attribute','Value'], parse_dates=['[간호기록]기록작성일시'], sheet_name=None)
    dfmvgcs = pd.concat([value.assign(sheet_source=key) for key,value in dfmvgcs.items()], ignore_index=True).drop('sheet_source', axis=1)
    dfmvgcs.columns = ['subject_id','charttime','attribute','value']
    dfmvgcs = dfmvgcs[~((dfmvgcs['attribute']=='ventilator 모드 종류') & (dfmvgcs['value']=='NIV-NAVA'))] # excluding NIV
    
    dfmvgcs = pd.read_csv('mv_gcs_2020_sample_data.csv.xz', parse_dates=['charttime'])
    
    # if not included in dtsart and dtend, should be removed because of null value
    dfmerge = pd.merge(dfmvgcs, dfor[['opid', 'orin', 'admissiontime', 'subject_id', 'dischargetime']], how='left', on = 'subject_id')
    dfmerge = dfmerge[dfmerge['opid'].notnull()]
    
    # only mv, gcs data within or admission time and discharge time
    dfmerge['dcnote'] = dfmerge.apply(lambda x: extract_wanted_period(x['admissiontime'], x['charttime'], x['dischargetime']), axis=1) 
    dfmerge = dfmerge[dfmerge.dcnote == 1]
    dfmerge['charttime'] = dfmerge.apply(lambda x: convert_to_relative_time(x['orin'], x['charttime']), axis=1)
    
    dfmerge.drop(['subject_id','admissiontime','dischargetime', 'dcnote', 'orin'], axis=1, inplace=True)    
    
    # 3-(1). gcs
    dfverbal = dfmerge[dfmerge['attribute'].str.contains('verbal', na=False)].sort_values(['opid','charttime']).reset_index(drop=True).dropna()
    
    # E, T -> mv(1) / 1,2,3 ... -> non-mv(0) 
    dfverbal.loc[dfverbal['value'].str.isalpha(), 'mv'] = 1
    dfverbal.loc[dfverbal['value'].str.isdigit(), 'mv'] = 0

    # gcs time search for each operation case
    vb_dfresult = pd.DataFrame(columns=['opid','charttime','attribute','value'])
    for opid in set(dfverbal.opid.values):
        data = dfverbal.loc[dfverbal['opid']==opid].reset_index(drop=True)

        # 1: only not mv, 0: only mv
        if data.mv.mean() == 1 or data.mv.mean() == 0 :
            continue
        
        # find cases that last 2 consecutive times after being replaced by a number
        for idx, row in data[data.mv==0].iterrows():
            dt = row['charttime']
        
            if data.iloc[idx-1]['mv'] == 0 and data.iloc[idx-2]['mv'] == 1:
                vb_dfresult = vb_dfresult.append(pd.Series([opid, dt, 'mv_gcs', 0], index=vb_dfresult.columns), ignore_index=True)
    
    # 3-(2). mv
    dfmv = dfmerge[~(dfmerge['attribute'].str.contains('verbal', na=False))]
    # merge with mv data to account for gcs 
    vb_mv_merge = dfmv.append(vb_dfresult, ignore_index=True).sort_values(['opid','charttime']).reset_index(drop=True).dropna()

    # mv time search for each operation case
    mv_dfresult = pd.DataFrame(columns=['opid','charttime','itemname','value'])
    for opid in vb_mv_merge['opid'].drop_duplicates().values: 
        
        data = vb_mv_merge[(vb_mv_merge['opid']==opid)]
        # remove values after the time labeled gcs
        try:
            data = data[:data[data['attribute']=='mv_gcs'].index.max()].reset_index(drop=True)
        except TypeError:
            data = data.reset_index(drop=True)
        
        # the maximum interval for ecmo is 8 hours
        idxes = list(data[data.charttime.diff(periods=-1) < -60*8].index)
        idxes.insert(0,-1)
        idxes.append(data.index.max())
        
        # search for idxes with a maximum interval lager than 8 hours and label all intermittent hours in those idxes as 1
        for idx in range(len(idxes)-1): 
            result = pd.DataFrame(range(data.iloc[idxes[idx]+1]['charttime'], data.iloc[idxes[idx+1]]['charttime']+1, 5), columns=['charttime'])
            result[['opid', 'itemname', 'value']] = [opid, 'mv', 1]
            mv_dfresult = mv_dfresult.append(result, ignore_index=False)
            
    print('done')
    
if not os.path.exists(operations_pickle_file):
    print('making...', operations_pickle_file)
    operations_df = make_operations_table(dtstart, dtend)
    pickle.dump(operations_df, open(operations_pickle_file, 'wb'))
    print(operations_df)
else: 
    print('using...', operations_pickle_file)
    operations_df = pickle.load(open(operations_pickle_file, 'rb'))
    
if not os.path.exists(diagnosis_pickle_file):
    print('making...', diagnosis_pickle_file)
    diagnosis_df = make_diagnosis_table(operations_df)
    pickle.dump(diagnosis_df, open(diagnosis_pickle_file, 'wb'))
    print(diagnosis_df)
else: 
    print('using...', diagnosis_pickle_file)
    diagnosis_df = pickle.load(open(diagnosis_pickle_file, 'rb'))

if not os.path.exists(labevents_pickle_file):
    print('making...', labevents_pickle_file)
    labevents_df = make_labevents_table(operations_df)
    pickle.dump(labevents_df, open(labevents_pickle_file, 'wb'))
    print(labevents_df)
else: 
    print('using...', labevents_pickle_file)
    labevents_df = pickle.load(open(labevents_pickle_file, 'rb'))

if not os.path.exists(vitals_pickle_file):
    print('making...', vitals_pickle_file)
    vitals_df = make_vitals_table(operations_df, dtstart, dtend)
    pickle.dump(vitals_df, open(vitals_pickle_file, 'wb'))
    print(vitals_df)
else: 
    print('using...', vitals_pickle_file)
    vitals_df = pickle.load(open(vitals_pickle_file, 'rb'))
    
if not os.path.exists(ward_vitals_pickle_file):
    print('making...', ward_vitals_pickle_file)
    ward_vitals_df = make_ward_vitals_table(operations_df)
    pickle.dump(ward_vitals_df, open(ward_vitals_pickle_file, 'wb'))
    print(ward_vitals_df)
else: 
    print('using...', ward_vitals_pickle_file)
    ward_vitals_df = pickle.load(open(ward_vitals_pickle_file, 'rb'))

# merge ward_vitals & vitals 
vitals_df = vitals_df.append(ward_vitals_df, ignore_index=True)
vitals_df = vitals_df.astype({'value':float})
vitals_df = vitals_df.groupby(['opid', 'charttime', 'itemname'], as_index=False).median()

# deidentified data
operations_df = deidentified_data(operations_df)
vitals_df = deidentified_data(vitals_df)
labevents_df = deidentified_data(labevents_df)
diagnosis_df = deidentified_data(diagnosis_df)

# operations_df replace time
convert_col_list = ['outtime','anstarttime','anendtime','opstarttime','opendtime','admissiontime','dischargetime','deathtime_inhosp']
for col in convert_col_list:
    operations_df[col] = operations_df.apply(lambda x: convert_to_relative_time(x['orin'], x[col]), axis=1) 
operations_df.drop(['orin', 'dehid', 'hid_adm'], axis=1, inplace=True) ########opname