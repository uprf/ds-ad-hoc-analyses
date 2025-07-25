import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from google.cloud import bigquery
import configparser
from google.cloud import bigquery_storage
import os, sys
import datetime
import pickle
import scipy
from matplotlib.backends.backend_pdf import PdfPages
from sklearn.linear_model import LinearRegression

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

config_path = '../config.ini'
config = configparser.ConfigParser()
config.read(config_path)

project_id = "streamamp-qa-239417"
client = bigquery.Client(project=project_id)
bqstorageclient = bigquery_storage.BigQueryReadClient()


def get_bq_data(query, replacement_dict={}):
    for k, v in replacement_dict.items():
        query = query.replace("{" + k + "}", f'{v}')

    result = client.query(query).result()
    if result is None:
        return

    return result.to_dataframe(bqstorage_client=bqstorageclient)

def get_data(query_filename, data_cache_filename, force_requery=False, repl_dict = {}):
    data_cache_filename_full = f'data_cache/{data_cache_filename}.pkl'

    if not force_requery and os.path.exists(data_cache_filename_full):
        print(f'found existing data_cache file, loading {data_cache_filename_full}')
        with open(data_cache_filename_full, 'rb') as f:
            df = pickle.load(f)
        return df

    query = open(os.path.join(sys.path[0], f"queries/{query_filename}.sql"), "r").read()
    df = get_bq_data(query, repl_dict)

    with open(data_cache_filename_full, 'wb') as f:
        pickle.dump(df, f)
    return df

def main_base():

    repl_dict = {'first_date': '2024-11-1',
                 'last_date': '2024-12-10'}

    query_file = 'query_floors_ad_unit_base'
    query = open(os.path.join(sys.path[0], f"queries/{query_file}.sql"), "r").read()
    get_bq_data(query, repl_dict)

def main():
    #main_ad_unit_filter('ad_unit_name = "/15184186/signupgenius_Desktop_SignUps_Sheet_300x600_Right"')

    for ad_unit_name in ['/22797863291/scribd_incontent_1',
                        '/22797863291/scribd_rightrail_adhesion',
                        '/22797863291/scribd_bottomright_mrec',
                        '/22797863291/scribd_adhesion',
                        '/22797863291/slideshare_adhesion']:

        main_ad_unit_filter(f'ad_unit_name = "{ad_unit_name}"')

def main_ad_unit_filter(ad_unit_filter):

    repl_dict = {'ad_unit_filter': ad_unit_filter}

    query_file = 'query_direct_targetting'
    query = open(os.path.join(sys.path[0], f"queries/{query_file}.sql"), "r").read()
    df = get_bq_data(query, repl_dict)

    plot_specs = [(['optimised_requests'], True), (['optimised_fill_rate'], False), (['optimised_cpm', 'optimised_cpma'], False)]

    fig, ax = plt.subplots(figsize=(16, 12), nrows=len(plot_specs))
    fig.suptitle(f'Flooring data_cache for: {repl_dict["ad_unit_filter"]}')

    for i, (cols, log_y) in enumerate(plot_specs):
        ax_i = ax[i]

        df[cols].plot(ax=ax_i, logy=log_y, style='x-')

    sp = ad_unit_filter.split('"')
    assert len(sp) >= 2
    sp1 = sp[1]
    assert len(sp1) > 2
    sp2 = sp1.split('/')[-1]
    assert len(sp2) > 2
    fig.savefig(f'plots_direct/plot_base_{sp2}.png')


def main_ad_unit_multiple():

    target_fill_rate = 0.7
    N = 40
    N_p = 8
    plot_specs = [(['optimised_requests'], True),
#                  (['optimised_fill_rate', 'pred_fill_rate'], False),
                  (['optimised_fill_rate'], False),
                  #(['optimised_cpma'], False)]
                  (['optimised_cpm', 'optimised_cpma'], False)]

    include_pred_fill_rate = len([0 for s in plot_specs if 'pred_fill_rate' in s[0]]) > 0

    query = f'select ad_unit_name from `streamamp-qa-239417.Floors_2_0.floors_ad_unit_dash` group by 1 order by sum(requests) desc limit {N}'
    df_ad_unit_name = get_bq_data(query)

    n_p = 0
    nn_p = 0
    with PdfPages(f'plots_direct/plots_pred_{include_pred_fill_rate}_pdf.pdf') as pdf:

        for i, ad_unit_name in enumerate(df_ad_unit_name['ad_unit_name']):
            if n_p==0:
                fig, ax = plt.subplots(figsize=(25, 20), nrows=N_p, ncols=len(plot_specs))

            repl_dict = {'ad_unit_filter': f'ad_unit_name = "{ad_unit_name}"'}
            query_file = 'query_direct_targetting'
            print(f'doing: {query_file} for: {repl_dict["ad_unit_filter"]}, {i} of {N}')
            df = get_data(query_file, ad_unit_name.replace('/', '_'), repl_dict=repl_dict, force_requery=True)
            df = df.set_index('floor_price')
            df = df[df['optimised_requests'] > 0]

            # fit_data = df.reset_index()[['floor_price', 'optimised_fill_rate', 'optimised_requests']].copy()
            # fit_data_ext = fit_data
            # bound_weight = df['optimised_requests'].sum() * 10
            # fit_data_ext = pd.concat([pd.DataFrame([[0, 1, bound_weight]], columns=['floor_price', 'optimised_fill_rate', 'optimised_requests']),
            #                           fit_data,
            #                           pd.DataFrame([[df.index.max() * 1.1, 0, bound_weight]], columns=['floor_price', 'optimised_fill_rate', 'optimised_requests'])])
            # fit_data_ext['ones'] = 1
            # fit_data_ext['floor_price_2'] = fit_data_ext[['floor_price']] ** 2
            # X = fit_data_ext[['ones', 'floor_price', 'floor_price_2']]
            # y = fit_data_ext['optimised_fill_rate']
            # regressor = LinearRegression(fit_intercept=False).fit(X, y, sample_weight=fit_data_ext['optimised_requests'])
            # y_pred = regressor.predict(X)
            # df['pred_fill_rate'] = y_pred[1:-1]

            if include_pred_fill_rate:
                X = -df.index.values.reshape(-1, 1)
                y = np.log(df['optimised_fill_rate'])
                regressor = LinearRegression(fit_intercept=False, positive=True).fit(X, y, sample_weight=df['optimised_requests'])
                df['pred_fill_rate'] = np.exp(regressor.predict(X))
                target_floor_price = min(-np.log(target_fill_rate) / regressor.coef_[0], (-X).max())

            for col_i, (cols, log_y) in enumerate(plot_specs):
                ax_ = ax[n_p, col_i]
                df[cols].plot(ax=ax_, logy=log_y, style='x-')
                if include_pred_fill_rate:
                    ax_.plot([target_floor_price, target_floor_price], [0, 1])

            if include_pred_fill_rate:
                ax[n_p, 0].set_ylabel(f'{ad_unit_name.split('/')[-1][:10]} {target_floor_price:0.2f}')
            #ax[n_p, 0].set_title(ad_unit_name.split('/')[-1])

            n_p += 1
            if (n_p==N_p) or (i==len(df_ad_unit_name['ad_unit_name'])-1):
                pdf.savefig()
                fig.savefig(f'plots_direct/plots_pred_{include_pred_fill_rate}_png_{nn_p}')
                n_p = 0
                nn_p += 1

def calculate_target_floor_price(df, floor_price_limit, cpma_col_name='optimised_cpma'):
    df_limit = df[df.index <= floor_price_limit]
    if df_limit[cpma_col_name].sum() == 0:
        return np.nan

    return (df_limit[cpma_col_name] * df_limit.index).sum() / df_limit[cpma_col_name].sum()

def main_ad_unit_multiple_price_pressure():

    ad_request_cum_prop_threshold = 0.975
    plots_name = 'price_pressure'
    N = 40
    N_p = 4
    target_fill_rate = 0.7
    limit_fill_rate = 0.1

    plot_specs = [(['optimised_requests'], True, False),
                  (['optimised_fill_rate', 'pred_fill_rate'], False, False),
                  (['optimised_cpma'], False, False),
                  (['optimised_cpma'], False, True)]

    # (['optimised_cpm', 'optimised_cpma'], False)]

    query = f'select ad_unit_name from `streamamp-qa-239417.Floors_2_0.floors_ad_unit_dash` group by 1 order by sum(requests) desc limit {N}'
    df_ad_unit_name = get_bq_data(query)

    n_p = 0
    nn_p = 0

    with PdfPages(f'plots_direct/plots_{plots_name}_pdf.pdf') as pdf:

        for i, ad_unit_name in enumerate(df_ad_unit_name['ad_unit_name']):
            if n_p == 0:
                fig, ax = plt.subplots(figsize=(25, 20), nrows=N_p, ncols=len(plot_specs))

            repl_dict = {'ad_unit_filter': f'ad_unit_name = "{ad_unit_name}"'}
            query_file = 'query_direct_targetting'
            print(f'doing: {query_file} for: {repl_dict["ad_unit_filter"]}, {i} of {N}')
            df = get_data(query_file, ad_unit_name.replace('/', '_'), repl_dict=repl_dict, force_requery=False)

            df_baseline = df[df['baseline_requests'] > 0]
            assert(len(df_baseline)==1)
            baseline_cpma = df_baseline['baseline_cpma'].iloc[0]

            df = df.set_index('floor_price')
            df = df[df['optimised_requests'] > 0]

            X = -df.index.values.reshape(-1, 1)
            y = np.log(df['optimised_fill_rate'])
            regressor = LinearRegression(fit_intercept=False, positive=True).fit(X, y,
                                                                                 sample_weight=df['optimised_requests'])
            df['pred_fill_rate'] = np.exp(regressor.predict(X))
            target_floor_price = min(-np.log(target_fill_rate) / regressor.coef_[0], (-X).max())
            floor_price_limit_fill_rate = min(-np.log(limit_fill_rate) / regressor.coef_[0], (-X).max())
            floor_price_limit_ad_request_threshold = df[df['optimised_requests'].cumsum() / df['optimised_requests'].sum() < ad_request_cum_prop_threshold].index.max()

            target_floor_price_limit_fill_rate = calculate_target_floor_price(df, floor_price_limit_fill_rate)
            target_floor_price_limit_ad_request_threshold = calculate_target_floor_price(df, floor_price_limit_ad_request_threshold)

            for col_i, (cols, log_y, limited) in enumerate(plot_specs):
                ax_ = ax[n_p, col_i]
                df[cols].plot(ax=ax_, logy=log_y, style='x-')

                if 'pred_fill_rate' in cols:
                    ax_.plot([target_floor_price, target_floor_price], [0, 1])

                if 'optimised_cpma' in cols:
                    # ax_.plot([df.index.min(), df.index.max()], [baseline_cpma, baseline_cpma])
                    # ax_.plot([target_floor_price_limit_fill_rate, target_floor_price_limit_fill_rate], [0, df[cols].max().max()])
                    # ax_.plot([target_floor_price_limit_ad_request_threshold, target_floor_price_limit_ad_request_threshold], [0, df[cols].max().max()])

                    fp1 = pd.DataFrame([0, df[cols].max().max()], columns=[f'cpma_weighted_fill_rate_limit_{limit_fill_rate*100:0.0f}'], index=pd.Index(
                        [target_floor_price_limit_fill_rate, target_floor_price_limit_fill_rate]))

                    fp2 = pd.DataFrame([0, df[cols].max().max()], columns=[f'cpma_weighted_ad_request_limit_{ad_request_cum_prop_threshold*100:0.1f}'], index=pd.Index(
                        [target_floor_price_limit_ad_request_threshold, target_floor_price_limit_ad_request_threshold]))

                    fp3 = pd.DataFrame([0, df[cols].max().max()], columns=[f'target_fill_rate_{target_fill_rate*100:0.0f}'], index=pd.Index(
                        [target_floor_price, target_floor_price]))

                    fp4 = pd.DataFrame([baseline_cpma, baseline_cpma], columns=['baseline_cpma'], index=pd.Index(
                        [df.index.min(), df.index.max()]))

                    fp = pd.concat([fp1, fp2, fp3, fp4])
                    fp.plot(ax=ax_)

                if limited:
                    ax_.set_xlim([0, 1.1 * max([target_floor_price_limit_fill_rate, target_floor_price_limit_ad_request_threshold, floor_price_limit_fill_rate])])

            ax[n_p, 0].set_ylabel(f'{ad_unit_name.split('/')[-1][:10]} {target_floor_price:0.2f}')
            # ax[n_p, 0].set_title(ad_unit_name.split('/')[-1])

            n_p += 1
            if (n_p == N_p) or (i == len(df_ad_unit_name['ad_unit_name']) - 1):
                pdf.savefig()
                fig.savefig(f'plots_direct/plots_{plots_name}_png_{nn_p}')
                n_p = 0
                nn_p += 1

def df_vert_line(x, y_min, y_max, name):
    return pd.DataFrame([y_min, y_max], columns=[name], index=pd.Index([x, x]))

def main_ad_unit_compare():
    ad_unit_count = 10000
    do_plots = False

    ad_request_cum_prop_threshold = 0.975
    target_fill_rate = 0.7
    limit_fill_rate = 0.1

    repl_dict = {'ad_unit_count': ad_unit_count}
    query_file = 'query_direct_targetting_multiple'

    print(f'doing: {query_file}')
    df_all = get_data(query_file, f'compare_multiple_{ad_unit_count}', repl_dict=repl_dict, force_requery=True)
    ad_unit_names = df_all['ad_unit_name'].unique()

    if do_plots:
        pdf = PdfPages(f'plots_direct/compare_pdf.pdf')
    target_floor_price_list = []
    for ad_unit_name in ad_unit_names:
        df = df_all[df_all['ad_unit_name'] == ad_unit_name]
        df = df[df['fill_rate'] > 0]
        if len(df) == 0:
            continue

        X = -df[['floor_price']]
        X_max = (-X).max().max()
        y = np.log(df['fill_rate'])
        fill_rate_regressor = LinearRegression(fit_intercept=False, positive=True).fit(X, y, sample_weight=df['requests'])
        lamb = fill_rate_regressor.coef_[0]

        X_cpm = df[['floor_price']]
        y = df['cpm']
        cpm_regressor = LinearRegression(fit_intercept=True, positive=True).fit(X_cpm, y, sample_weight=df['requests'])
        alpha = cpm_regressor.intercept_
        beta = cpm_regressor.coef_[0]

        df = df.set_index('floor_price')

        if lamb == 0:
            target_floor_price = np.nan
            target_floor_price_limit_fill_rate = np.nan
        else:
            if beta == 0:
                target_floor_price_max_cpma = 0
            else:
                target_floor_price_max_cpma = max(min(1 / lamb - alpha / beta, X_max), 0)
            target_floor_price = min(-np.log(target_fill_rate) / lamb, X_max)
            floor_price_limit_fill_rate = min(-np.log(limit_fill_rate) / lamb, X_max)
            target_floor_price_limit_fill_rate = min(calculate_target_floor_price(df, floor_price_limit_fill_rate, 'cpma'), X_max)

        floor_price_limit_ad_request_threshold = df[df['requests'].cumsum() / df['requests'].sum() < ad_request_cum_prop_threshold].index.max()
        target_floor_price_limit_ad_request_threshold = min(calculate_target_floor_price(df, floor_price_limit_ad_request_threshold, 'cpma'), X_max)

        target_floor_price_list.append({'ad_unit_name': ad_unit_name,
                                        'cpma_weighted_limit_fill_rate': target_floor_price_limit_fill_rate,
                                        'cpma_weighted_limit_ad_request_threshold': target_floor_price_limit_ad_request_threshold,
                                        'max_cpma_dual_model': target_floor_price_max_cpma,
                                        'target_fill_rate': target_floor_price})

        if do_plots:
            fig, ax = plt.subplots(figsize=(16, 12), nrows=2)
            df_plot = df.copy()

            df_plot['pred_fill_rate'] = np.exp(fill_rate_regressor.predict(X))
            df_plot['pred_cpm'] = cpm_regressor.predict(X_cpm)
            df_plot['pred_cpma'] = df_plot['pred_cpm'] * df_plot['pred_fill_rate']

            y_max = 1
            fp1 = df_vert_line(target_floor_price_limit_fill_rate, 0, y_max,
                               f'cpma_weighted_fill_rate_limit_{limit_fill_rate * 100:0.0f}: {target_floor_price_limit_fill_rate:0.2f}')
            fp2 = df_vert_line(target_floor_price_limit_ad_request_threshold, 0, y_max,
                               f'cpma_weighted_ad_request_limit_{ad_request_cum_prop_threshold * 100:0.1f}: {target_floor_price_limit_ad_request_threshold:0.2f}')
            fp3 = df_vert_line(target_floor_price, 0, y_max,
                               f'target_fill_rate_{target_fill_rate * 100:0.0f}: {target_floor_price:0.2f}')
            fp4 = df_vert_line(target_floor_price_max_cpma, 0, y_max,
                               f'target_floor_price_max_cpma: {target_floor_price_max_cpma:0.2f}')
            fp = pd.concat([fp1, fp2, fp3, fp4])
            df_plot[['fill_rate', 'pred_fill_rate']].plot(ax=ax[0], legend=None)
            fp.plot(ax=ax[0])

            x_max = 3
            y_max = df_plot[df_plot.index <= x_max].iloc[-1]['cpm']
            fp1 = df_vert_line(target_floor_price_limit_fill_rate, 0, y_max,
                               f'cpma_weighted_fill_rate_limit_{limit_fill_rate * 100:0.0f}: {target_floor_price_limit_fill_rate:0.2f}')
            fp2 = df_vert_line(target_floor_price_limit_ad_request_threshold, 0, y_max,
                               f'cpma_weighted_ad_request_limit_{ad_request_cum_prop_threshold * 100:0.1f}: {target_floor_price_limit_ad_request_threshold:0.2f}')
            fp3 = df_vert_line(target_floor_price, 0, y_max,
                               f'target_fill_rate_{target_fill_rate * 100:0.0f}: {target_floor_price:0.2f}')
            fp4 = df_vert_line(target_floor_price_max_cpma, 0, y_max,
                               f'target_floor_price_max_cpma: {target_floor_price_max_cpma:0.2f}')
            fp = pd.concat([fp1, fp2, fp3, fp4])

            df_plot[['cpm', 'pred_cpm', 'cpma', 'pred_cpma']].plot(ax=ax[1], legend=None)
            fp.plot(ax=ax[1])
            ax[1].set_xlim([0, x_max])
            ax[1].set_ylim([0, y_max])
            pdf.savefig()


    if do_plots:
        pdf.close()

    df_target_floor_price = pd.DataFrame(target_floor_price_list)
    df_target_floor_price.to_csv(f'plots_direct/df_target_floor_price_{ad_unit_count}.csv')

def main_ad_unit_compare_do_plots(filename, x_col='cpma_weighted_limit_ad_request_threshold', y_cols=['cpma_weighted_limit_fill_rate', 'target_fill_rate', 'max_cpma_dual_model']):
    ad_unit_count = 10000
#    df = pd.read_csv(f'plots_direct/df_target_floor_price_{ad_unit_count}.csv')

    df = pd.read_csv(f'plots_direct/{filename}.csv')

    if x_col is None:
        x_col = df.columns[0]

    if y_cols is None:
        y_cols = df.columns[1:]

    for y_col in y_cols:
        fig, ax = plt.subplots(figsize=(16, 12))

        df_reg = df[df[[x_col, y_col]].isna().sum(axis=1) == 0]
        X = df_reg[[x_col]]
        X_max = X.max().max()
        y = df_reg[y_col]
        regressor = LinearRegression(fit_intercept=False).fit(X, y)
        coef = regressor.coef_[0]
        r_squared = regressor.score(X, y)

        df.plot.scatter(x_col, y_col, ax=ax, title=f'{y_col} ~ {coef:0.2f} x {x_col}, R^2={r_squared*100:0.0f}%')
        ax.plot([0, X_max], [0, X_max*coef], 'r-')

        fig.savefig(f'plots_direct/{filename}_scatterplot_{y_col}.png')



def main_ad_unit_compare_limit_fill_rate():

    ad_request_cum_prop_threshold = 0.975
    limit_fill_rates = [0.1, 0.2, 0.3, 0.4, 0.5]

    repl_dict = {'ad_unit_count': 10000}
    query_file = 'query_direct_targetting_multiple'

    print(f'doing: {query_file}')
    df_all = get_data(query_file, f'compare_multiple_{repl_dict["ad_unit_count"]}', repl_dict=repl_dict, force_requery=False)
    ad_unit_names = df_all['ad_unit_name'].unique()

    results_list = []
    for ad_unit_name in ad_unit_names:
        df = df_all[df_all['ad_unit_name'] == ad_unit_name]
        df = df[df['fill_rate'] > 0]
        if len(df) == 0:
            continue

        X = -df[['floor_price']]
        X_max = (-X).max().max()
        y = np.log(df['fill_rate'])
        regressor = LinearRegression(fit_intercept=False, positive=True).fit(X, y, sample_weight=df['requests'])

        df = df.set_index('floor_price')
        floor_price_limit_ad_request_threshold = df[df['requests'].cumsum() / df['requests'].sum() < ad_request_cum_prop_threshold].index.max()
        target_floor_price_limit_ad_request_threshold = min(calculate_target_floor_price(df, floor_price_limit_ad_request_threshold, 'cpma'), X_max)

        if regressor.coef_[0] == 0:
            continue

        results = {'ad_unit_name': ad_unit_name,
                   'target_floor_price_limit_ad_request_threshold': target_floor_price_limit_ad_request_threshold}

        for limit_fill_rate in limit_fill_rates:
            floor_price_limit_fill_rate = min(-np.log(limit_fill_rate) / regressor.coef_[0], X_max)
            target_floor_price_limit_fill_rate = min(calculate_target_floor_price(df, floor_price_limit_fill_rate, 'cpma'), X_max)
            results[f'cpma_weighted_limit_fill_rate_{limit_fill_rate*100:0.0f}'] = target_floor_price_limit_fill_rate
        results_list.append(results)

    df = pd.DataFrame(results_list)
    df.to_csv(f'plots_direct/df_target_floor_price_limit_fill_rate_{repl_dict["ad_unit_count"]}.csv')

def main_ad_unit_compare_limit_fill_rate_do_table(ad_unit_count=10000):

    df = pd.read_csv(f'plots_direct/df_target_floor_price_limit_fill_rate_{ad_unit_count}.csv')

    x_col = 'target_floor_price_limit_ad_request_threshold'
    results_list = []
    for y_col in [c for c in df.columns if 'cpma_weighted_limit_fill_rate' in c]:

        df_reg = df[df[[x_col, y_col]].isna().sum(axis=1) == 0]
        X = df_reg[[x_col]]
        X_max = X.max().max()
        y = df_reg[y_col]
        regressor = LinearRegression(fit_intercept=False).fit(X, y)
        coef = regressor.coef_[0]
        r_squared = regressor.score(X, y)
        results_list.append({'name': y_col, 'coef': coef, 'r_squared': r_squared})

    df = pd.DataFrame(results_list)
    df.to_csv(f'plots_direct/main_ad_unit_compare_limit_fill_rate_do_plots_{ad_unit_count}.csv', )
    h = 0


def main_ad_unit_cpm_model():
    ad_unit_count = 40
    do_plots = True
    N_p = 8
    N = ad_unit_count

    ad_request_cum_prop_threshold = 0.975
    target_fill_rate = 0.7
    limit_fill_rate = 0.1

    repl_dict = {'ad_unit_count': ad_unit_count}
    query_file = 'query_direct_targetting_multiple'

    print(f'doing: {query_file}')
    df_all = get_data(query_file, f'compare_multiple_{ad_unit_count}', repl_dict=repl_dict, force_requery=True)
    ad_unit_names = df_all['ad_unit_name'].unique()

    N_i = 0
    N_p_i = 0
    NN_p = 0
    if do_plots:
        pdf = PdfPages(f'plots_direct/compare_cpm_model_pdf.pdf')
    target_floor_price_list = []
    for ad_unit_name in ad_unit_names:
        df = df_all[df_all['ad_unit_name'] == ad_unit_name]
        df = df[df['fill_rate'] > 0]
        if len(df) == 0:
            continue

        X = -df[['floor_price']]
        X_max = (-X).max().max()
        y = np.log(df['fill_rate'])
        fill_rate_regressor = LinearRegression(fit_intercept=False, positive=True).fit(X, y, sample_weight=df['requests'])
        lamb = fill_rate_regressor.coef_[0]

        X_cpm = df[['floor_price']]
        y = df['cpm']
        cpm_regressor = LinearRegression(fit_intercept=True, positive=True).fit(X_cpm, y, sample_weight=df['requests'])
        alpha = cpm_regressor.intercept_
        beta = cpm_regressor.coef_[0]

        df = df.set_index('floor_price')

        if lamb == 0:
            target_floor_price = np.nan
            target_floor_price_limit_fill_rate = np.nan
        else:
            target_floor_price_max_cpma = max(min(1 / lamb - alpha / beta, X_max), 0)
            target_floor_price = min(-np.log(target_fill_rate) / lamb, X_max)
            floor_price_limit_fill_rate = min(-np.log(limit_fill_rate) / lamb, X_max)
            target_floor_price_limit_fill_rate = min(
                calculate_target_floor_price(df, floor_price_limit_fill_rate, 'cpma'), X_max)

        floor_price_limit_ad_request_threshold = df[
            df['requests'].cumsum() / df['requests'].sum() < ad_request_cum_prop_threshold].index.max()
        target_floor_price_limit_ad_request_threshold = min(
            calculate_target_floor_price(df, floor_price_limit_ad_request_threshold, 'cpma'), X_max)

        target_floor_price_list.append({'ad_unit_name': ad_unit_name,
                                        'cpma_weighted_limit_fill_rate': target_floor_price_limit_fill_rate,
                                        'cpma_weighted_limit_ad_request_threshold': target_floor_price_limit_ad_request_threshold,
                                        'target_fill_rate': target_floor_price})

        if do_plots and (N_i < N):
            if N_p_i == 0:
                fig, ax = plt.subplots(figsize=(20, 16), ncols=2, nrows=N_p)

            df_plot = df.copy()
            df_plot['pred_fill_rate'] = np.exp(fill_rate_regressor.predict(X))
            df_plot['pred_cpm'] = cpm_regressor.predict(X_cpm)
            df_plot['pred_cpma'] = df_plot['pred_cpm'] * df_plot['pred_fill_rate']

            y_max = 1
            fp1 = df_vert_line(target_floor_price_limit_fill_rate, 0, y_max,
                               f'cpma_weighted_fill_rate_limit_{limit_fill_rate * 100:0.0f}: {target_floor_price_limit_fill_rate:0.2f}')
            fp2 = df_vert_line(target_floor_price_limit_ad_request_threshold, 0, y_max,
                               f'cpma_weighted_ad_request_limit_{ad_request_cum_prop_threshold * 100:0.1f}: {target_floor_price_limit_ad_request_threshold:0.2f}')
            fp3 = df_vert_line(target_floor_price, 0, y_max,
                               f'target_fill_rate_{target_fill_rate * 100:0.0f}: {target_floor_price:0.2f}')
            fp4 = df_vert_line(target_floor_price_max_cpma, 0, y_max,
                               f'target_floor_price_max_cpma: {target_floor_price_max_cpma:0.2f}')
            fp = pd.concat([fp1, fp2, fp3, fp4])
            df_plot[['fill_rate', 'pred_fill_rate']].plot(ax=ax[N_p_i, 0], legend=None)
            fp.plot(ax=ax[N_p_i, 0], legend=None)

            x_max = 3
            y_max = df_plot[df_plot.index <= x_max].iloc[-1]['cpm']
            fp1 = df_vert_line(target_floor_price_limit_fill_rate, 0, y_max,
                               f'cpma_weighted_fill_rate_limit_{limit_fill_rate * 100:0.0f}: {target_floor_price_limit_fill_rate:0.2f}')
            fp2 = df_vert_line(target_floor_price_limit_ad_request_threshold, 0, y_max,
                               f'cpma_weighted_ad_request_limit_{ad_request_cum_prop_threshold * 100:0.1f}: {target_floor_price_limit_ad_request_threshold:0.2f}')
            fp3 = df_vert_line(target_floor_price, 0, y_max,
                               f'target_fill_rate_{target_fill_rate * 100:0.0f}: {target_floor_price:0.2f}')
            fp4 = df_vert_line(target_floor_price_max_cpma, 0, y_max,
                               f'target_floor_price_max_cpma: {target_floor_price_max_cpma:0.2f}')
            fp = pd.concat([fp1, fp2, fp3, fp4])

            df_plot[['cpm', 'pred_cpm']].plot(ax=ax[N_p_i, 1], legend=None)
            fp.plot(ax=ax[N_p_i, 1], legend=None)
            ax[N_p_i, 1].set_xlim([0, x_max])
            ax[N_p_i, 1].set_ylim([0, y_max])

            N_p_i += 1
            if N_p_i == N_p:
                fig.savefig(f'plots_direct/compare_cpm_model_png_{NN_p}.png')
                pdf.savefig()
                NN_p += 1
                N_p_i = 0

    if do_plots:
        pdf.close()


def main_ad_unit_combined_model():
    ad_unit_count = 40
    do_plots = True
    N_p = 8
    N = ad_unit_count
    plotname = 'compare_combined_model_log_log'

    ad_request_cum_prop_threshold = 0.975
    target_fill_rate = 0.7
    limit_fill_rate = 0.1

    repl_dict = {'ad_unit_count': ad_unit_count}
    query_file = 'query_direct_targetting_multiple'

    print(f'doing: {query_file}')
    df_all = get_data(query_file, f'compare_multiple_{ad_unit_count}', repl_dict=repl_dict, force_requery=False)
    ad_unit_names = df_all['ad_unit_name'].unique()

    N_i = 0
    N_p_i = 0
    NN_p = 0
    if do_plots:
        pdf = PdfPages(f'plots_direct/{plotname}_pdf.pdf')
    target_floor_price_list = []
    for ad_unit_name in ad_unit_names:
        df = df_all[df_all['ad_unit_name'] == ad_unit_name]
        df = df[df['fill_rate'] > 0]
        if len(df) == 0:
            continue

        df = df[df['floor_price'] <= 18]

        X = -df[['floor_price']]
        X_max = (-X).max().max()
        y = np.log(df['fill_rate'])
        fill_rate_regressor = LinearRegression(fit_intercept=True, positive=True).fit(X, y, sample_weight=df['requests'])
        lamb = fill_rate_regressor.coef_[0]
        F0 = np.exp(fill_rate_regressor.intercept_)

        X_cpm = df[['floor_price']]
        y_cpm = df['cpm']
        cpm_regressor = LinearRegression(fit_intercept=True, positive=True).fit(X_cpm, y_cpm, sample_weight=df['requests'])
        alpha = cpm_regressor.intercept_
        beta = cpm_regressor.coef_[0]

        y_ln = np.log(df['fill_rate'])
        X_ln = -np.log(df[['floor_price']])
        pow_fill_rate_regressor = LinearRegression(fit_intercept=True, positive=True).fit(X_ln, y_ln, sample_weight=df['requests'])
        alpha_ln_ln = pow_fill_rate_regressor.intercept_
        beta_ln_ln = pow_fill_rate_regressor.coef_[0]

        y_ln = np.log(df['fill_rate'])
        X_ln_n = -pd.concat([np.log(df[['floor_price']]), df[['floor_price']]], axis=1)
        pow_exp_fill_rate_regressor = LinearRegression(fit_intercept=False, positive=True).fit(X_ln_n, y_ln, sample_weight=df['requests'])

        y_ln_ln = np.log(-np.log(df['fill_rate']))
        X_ln_ln = np.log(df[['floor_price']])
        exp_pow_fill_rate_regressor = LinearRegression(fit_intercept=True, positive=True).fit(X_ln_ln, y_ln_ln, sample_weight=df['requests'])

        y_ln_ln = np.log(-np.log(df['fill_rate']))
        X_ln_ln = np.log(df[['floor_price']])
        exp_pow_2_fill_rate_regressor = LinearRegression(fit_intercept=False, positive=True).fit(X_ln_ln, y_ln_ln, sample_weight=df['requests'])

        df = df.set_index('floor_price')

        if lamb == 0:
            target_floor_price = np.nan
            target_floor_price_limit_fill_rate = np.nan
        else:
            target_floor_price_max_cpma = max(min(1 / lamb - alpha / beta, X_max), 0)
            target_floor_price = max(0, min(-np.log(target_fill_rate / F0) / lamb, X_max))
            floor_price_limit_fill_rate = max(0, min(-np.log(limit_fill_rate / F0) / lamb, X_max))
            target_floor_price_limit_fill_rate = min(
                calculate_target_floor_price(df, floor_price_limit_fill_rate, 'cpma'), X_max)

        floor_price_limit_ad_request_threshold = df[
            df['requests'].cumsum() / df['requests'].sum() < ad_request_cum_prop_threshold].index.max()
        target_floor_price_limit_ad_request_threshold = min(
            calculate_target_floor_price(df, floor_price_limit_ad_request_threshold, 'cpma'), X_max)

        target_floor_price_list.append({'ad_unit_name': ad_unit_name,
                                        'cpma_weighted_limit_fill_rate': target_floor_price_limit_fill_rate,
                                        'cpma_weighted_limit_ad_request_threshold': target_floor_price_limit_ad_request_threshold,
                                        'target_fill_rate': target_floor_price})

        if do_plots and (N_i < N):
            if N_p_i == 0:
                fig, ax = plt.subplots(figsize=(20, 16), ncols=2, nrows=N_p)

            df_plot = df.copy()
            df_plot['pred_fill_rate'] = np.exp(fill_rate_regressor.predict(X))
            df_plot['pred_fill_rate_pow'] = np.exp(pow_fill_rate_regressor.predict(X_ln))
            df_plot['pred_fill_rate_pow_exp'] = np.exp(pow_exp_fill_rate_regressor.predict(X_ln_n))
            df_plot['pred_fill_rate_exp_pow'] = np.exp(-np.exp(exp_pow_fill_rate_regressor.predict(X_ln_ln)))
            df_plot['pred_fill_rate_exp_pow_2'] = np.exp(-np.exp(exp_pow_2_fill_rate_regressor.predict(X_ln_ln)))

            df_plot['pred_cpm'] = cpm_regressor.predict(X_cpm)
            df_plot['pred_cpma'] = df_plot['pred_cpm'] * df_plot['pred_fill_rate']

            y_max = 1
            fp1 = df_vert_line(target_floor_price_limit_fill_rate, 0, y_max,
                               f'cpma_weighted_fill_rate_limit_{limit_fill_rate * 100:0.0f}: {target_floor_price_limit_fill_rate:0.2f}')
            fp2 = df_vert_line(target_floor_price_limit_ad_request_threshold, 0, y_max,
                               f'cpma_weighted_ad_request_limit_{ad_request_cum_prop_threshold * 100:0.1f}: {target_floor_price_limit_ad_request_threshold:0.2f}')
            fp3 = df_vert_line(target_floor_price, 0, y_max,
                               f'target_fill_rate_{target_fill_rate * 100:0.0f}: {target_floor_price:0.2f}')
            fp4 = df_vert_line(target_floor_price_max_cpma, 0, y_max,
                               f'target_floor_price_max_cpma: {target_floor_price_max_cpma:0.2f}')
            fp = pd.concat([fp1, fp2, fp3, fp4])
            df_plot[['fill_rate', 'pred_fill_rate', 'pred_fill_rate_pow', 'pred_fill_rate_pow_exp', 'pred_fill_rate_exp_pow', 'pred_fill_rate_exp_pow_2']].plot(ax=ax[N_p_i, 0])#, legend=None)
            fp.plot(ax=ax[N_p_i, 0], legend=None)

            x_max = 3
            y_max = df_plot[df_plot.index <= x_max].iloc[-1]['cpm']
            fp1 = df_vert_line(target_floor_price_limit_fill_rate, 0, y_max,
                               f'cpma_weighted_fill_rate_limit_{limit_fill_rate * 100:0.0f}: {target_floor_price_limit_fill_rate:0.2f}')
            fp2 = df_vert_line(target_floor_price_limit_ad_request_threshold, 0, y_max,
                               f'cpma_weighted_ad_request_limit_{ad_request_cum_prop_threshold * 100:0.1f}: {target_floor_price_limit_ad_request_threshold:0.2f}')
            fp3 = df_vert_line(target_floor_price, 0, y_max,
                               f'target_fill_rate_{target_fill_rate * 100:0.0f}: {target_floor_price:0.2f}')
            fp4 = df_vert_line(target_floor_price_max_cpma, 0, y_max,
                               f'target_floor_price_max_cpma: {target_floor_price_max_cpma:0.2f}')
            fp = pd.concat([fp1, fp2, fp3, fp4])

            df_plot[['cpm', 'pred_cpm']].plot(ax=ax[N_p_i, 1], legend=None)
            fp.plot(ax=ax[N_p_i, 1], legend=None)
            ax[N_p_i, 1].set_xlim([0, x_max])
            ax[N_p_i, 1].set_ylim([0, y_max])

            N_p_i += 1
            if N_p_i == N_p:
                fig.savefig(f'plots_direct/{plotname}_png_{NN_p}.png')
                pdf.savefig()
                NN_p += 1
                N_p_i = 0

    if do_plots:
        pdf.close()

def fit_model(X, y, fit_intercept, fit_method, df, positive=True):

    if np.isinf(X).any().any() or np.isinf(y).any():
        print('skipping because of inf')
        return np.ones(len(df)) * np.nan

    assert fit_method in ['weighted', 'request_limit']
    if fit_method == 'weighted':
        reg = LinearRegression(fit_intercept=fit_intercept, positive=positive).fit(X, y, sample_weight=df['requests'])
    else:
        reg = LinearRegression(fit_intercept=fit_intercept, positive=positive).fit(X, y)
    return reg.predict(X)


def fill_rate_modelling():

    ad_unit_count = 1000
    do_plots = True
    N_p = 8
    N_plot = min(40, ad_unit_count)
    plotname = 'fill_rate_modelling'

    ad_request_cum_prop_threshold = 0.975

    repl_dict = {'ad_unit_count': ad_unit_count}
    query_file = 'query_direct_targetting_multiple'

    print(f'doing: {query_file}')
    df_all = get_data(query_file, f'compare_multiple_{ad_unit_count}', repl_dict=repl_dict, force_requery=False)
    ad_unit_names = df_all['ad_unit_name'].unique()

    N_i = 0
    N_p_i = 0
    NN_p = 0
    if do_plots:
        pdf = PdfPages(f'plots_direct/{plotname}_{ad_unit_count}_pdf.pdf')

    results_dict = {}
    for ad_unit_name in ad_unit_names:
        results_dict[ad_unit_name] = {}
        df_ad = df_all[df_all['ad_unit_name'] == ad_unit_name]
        df_ad = df_ad[df_ad['fill_rate'] > 0]
        if len(df_ad) == 0:
            continue

        df_ad = df_ad[df_ad['floor_price'] <= 18]
        for fm_i, fit_method in enumerate(['weighted', 'request_limit']):

            df = df_ad.copy()
            if fit_method == 'request_limit':
                df = df[df['requests'].cumsum() / df['requests'].sum() < ad_request_cum_prop_threshold]

            for fit_intercept in [False, True]:

                df[f'cpm_model_{fit_method}_{fit_intercept}'] = fit_model(df[['floor_price']], df['cpm'], fit_intercept, fit_method, df)

                df[f'fill_rate_exp_{fit_method}_{fit_intercept}'] = np.exp(fit_model(-df[['floor_price']], np.log(df['fill_rate']), fit_intercept, fit_method, df))

                df[f'fill_rate_power_law_{fit_method}_{fit_intercept}'] = np.exp(fit_model(-np.log(df[['floor_price']]), np.log(df['fill_rate']), fit_intercept, fit_method, df))

                df[f'fill_rate_combined_exp_power_law_{fit_method}_{fit_intercept}'] = np.exp(fit_model(-pd.concat([np.log(df[['floor_price']]), df[['floor_price']]], axis=1),
                                                                np.log(df['fill_rate']), fit_intercept, fit_method, df))

                df[f'fill_rate_exp_of_power_law_{fit_method}_{fit_intercept}'] = np.exp(-np.exp(fit_model(np.log(df[['floor_price']]), np.log(-np.log(df['fill_rate'])), fit_intercept, fit_method, df)))

            df = df.set_index('floor_price')
            cols = [c for c in df.columns if 'fill_rate' in c]
            df_error = df[cols].apply(lambda x: x - x['fill_rate'], axis=1)

            results_dict[ad_unit_name].update(dict(zip([f'{c}_mae' for c in df_error.columns], np.abs(df_error).mean().values)))
            results_dict[ad_unit_name].update(dict(zip([f'{c}_mae_norm' for c in df_error.columns], (np.abs(df_error).mean() / df[cols].mean()).values)))

            if do_plots and (N_i < N_plot):
                if (N_p_i == 0) and (fm_i == 0):
                    fig, ax = plt.subplots(figsize=(24, 20), ncols=4, nrows=N_p)

                df[cols].plot(ax=ax[N_p_i, fm_i * 2], legend=None)
                df_error.plot(ax=ax[N_p_i, fm_i * 2 + 1], legend=None)

                if (N_p_i == 0):
                    ax[N_p_i, fm_i * 2].set_title(f'fill_rate: {fit_method}')
                    ax[N_p_i, fm_i * 2 + 1].set_title(f'residual: {fit_method}')

                if (fm_i == 0):
                    ax[N_p_i, fm_i * 2].set_ylabel(f'{NN_p+1}{N_p_i+1}: {ad_unit_name.split('/')[-1][:11]}')

                if fm_i == 1:
                    N_p_i += 1
                    if N_p_i == N_p:
                        fig.savefig(f'plots_direct/{plotname}_png_{ad_unit_count}_{NN_p}.png')
                        pdf.savefig()
                        NN_p += 1
                        N_p_i = 0

    if do_plots:
        pdf.close()

    results_all = pd.DataFrame(results_dict).transpose()
    results_all.to_csv(f'plots_direct/{plotname}_all_results_{ad_unit_count}.csv')

    results_summary = pd.concat([results_all.mean().to_frame('mean'), results_all.std().to_frame('std')], axis=1)
    results_summary.to_csv(f'plots_direct/{plotname}_summary_results_{ad_unit_count}.csv')

def fill_rate_modelling_selected():

    ad_unit_count = 40
    do_plots = True
    N_p = 8
    N_plot = min(40, ad_unit_count)
    plotname = 'fill_rate_modelling_selected'

    ad_request_cum_prop_threshold = 0.975

    repl_dict = {'ad_unit_count': ad_unit_count}
    query_file = 'query_direct_targetting_multiple'

    print(f'doing: {query_file}')
    df_all = get_data(query_file, f'compare_multiple_{ad_unit_count}', repl_dict=repl_dict, force_requery=False)
    ad_unit_names = df_all['ad_unit_name'].unique()

    N_i = 0
    N_p_i = 0
    NN_p = 0
    if do_plots:
        pdf = PdfPages(f'plots_direct/{plotname}_{ad_unit_count}_pdf.pdf')

    for ad_unit_name in ad_unit_names:
        df_ad = df_all[df_all['ad_unit_name'] == ad_unit_name]
        df_ad = df_ad[df_ad['fill_rate'] > 0]
        if len(df_ad) == 0:
            continue

        df_ad = df_ad[df_ad['floor_price'] <= 18]
        fit_method = 'request_limit'

        df = df_ad.copy()
        if fit_method == 'request_limit':
            df = df[df['requests'].cumsum() / df['requests'].sum() < ad_request_cum_prop_threshold]

        for fit_intercept in [False, True]:

            df[f'cpm_model_{fit_method}_{fit_intercept}'] = fit_model(df[['floor_price']], df['cpm'], fit_intercept, fit_method, df)

            df[f'fill_rate_exp_{fit_method}_{fit_intercept}'] = np.exp(fit_model(-df[['floor_price']], np.log(df['fill_rate']), fit_intercept, fit_method, df))

            df[f'fill_rate_power_law_{fit_method}_{fit_intercept}'] = np.exp(fit_model(-np.log(df[['floor_price']]), np.log(df['fill_rate']), fit_intercept, fit_method, df))

            df[f'fill_rate_combined_exp_power_law_{fit_method}_{fit_intercept}'] = np.exp(fit_model(-pd.concat([np.log(df[['floor_price']]), df[['floor_price']]], axis=1),
                                                            np.log(df['fill_rate']), fit_intercept, fit_method, df))

            df[f'fill_rate_exp_of_power_law_{fit_method}_{fit_intercept}'] = np.exp(-np.exp(fit_model(np.log(df[['floor_price']]), np.log(-np.log(df['fill_rate'])), fit_intercept, fit_method, df)))

        df = df.set_index('floor_price')
        cols = ['fill_rate', 'fill_rate_combined_exp_power_law_request_limit_False', 'fill_rate_exp_request_limit_True',
                'fill_rate_combined_exp_power_law_request_limit_True', 'fill_rate_exp_of_power_law_request_limit_True']

        if do_plots and (N_i < N_plot):
            if (N_p_i == 0):
                fig, ax = plt.subplots(figsize=(20, 16), ncols=2, nrows=round(N_p/2))
                ax = ax.flatten()

            df[cols].plot(ax=ax[N_p_i], ylabel=f'{NN_p+1}{N_p_i+1}: {ad_unit_name.split('/')[-1][:11]}')

            N_p_i += 1
            if N_p_i == N_p:
                fig.savefig(f'plots_direct/{plotname}_png_{ad_unit_count}_{NN_p}.png')
                pdf.savefig()
                NN_p += 1
                N_p_i = 0

    if do_plots:
        pdf.close()


def fill_rate_modelling_raw():
    ad_request_cum_prop_thresholds = [0.90, 0.95, 0.975]
    ad_unit_count = 40
    N_p = 4
    N = ad_unit_count
    plotname = 'fill_rate_modelling_raw'

    repl_dict = {'ad_unit_count': ad_unit_count}
    query_file = 'query_direct_targetting_multiple'

    print(f'doing: {query_file}')
    df_all = get_data(query_file, f'compare_multiple_{ad_unit_count}', repl_dict=repl_dict, force_requery=False)
    ad_unit_names = df_all['ad_unit_name'].unique()

    N_i = 0
    N_p_i = 0
    NN_p = 0
    with PdfPages(f'plots_direct/{plotname}_pdf.pdf') as pdf:
        for ad_unit_name in ad_unit_names:
            df = df_all[df_all['ad_unit_name'] == ad_unit_name]

            df = df.set_index('floor_price')
            if N_p_i == 0:
                fig, ax = plt.subplots(figsize=(20, 16), ncols=1, nrows=N_p)

            df[['fill_rate']].plot(ax=ax[N_p_i], ylabel=f'{NN_p+1}{N_p_i+1}')
            df[['requests']].plot(ax=ax[N_p_i], secondary_y=True)

            thresh_list = []
            for thresh in ad_request_cum_prop_thresholds:
                fp_thresh = df[df['requests'].cumsum() / df['requests'].sum() < thresh].index.max()
                thresh_list.append(df_vert_line(fp_thresh, 0, 1, f'requests_{thresh*100:0.1f}%, fp: {fp_thresh:0.2f}'))
            pd.concat(thresh_list).plot(ax=ax[N_p_i])

            N_p_i += 1
            if N_p_i == N_p:
                fig.savefig(f'plots_direct/{plotname}_png_{NN_p}.png')
                pdf.savefig()
                NN_p += 1
                N_p_i = 0

def target_floor_price_from_fill_rate(fill_rate, target_fill_rate):
    if fill_rate.iloc[0] < target_fill_rate:
        return 0
    if fill_rate.iloc[-1] > target_fill_rate:
        return np.nan
    return abs(fill_rate - target_fill_rate).idxmin()

def main_ad_unit_combined_model_v2(target_fill_rate=0.7):
    ad_unit_count = 1000
    do_plots = True
    N_p = 8
    N = 40
    plotname = f'compare_combined_model_v2_{target_fill_rate*100:0.0f}'

    ad_request_cum_prop_threshold = 0.975

    repl_dict = {'ad_unit_count': ad_unit_count}
    query_file = 'query_direct_targetting_multiple'

    print(f'doing: {query_file}')
    df_all = get_data(query_file, f'compare_multiple_{ad_unit_count}', repl_dict=repl_dict, force_requery=False)
    ad_unit_names = df_all['ad_unit_name'].unique()

    N_i = 0
    N_p_i = 0
    NN_p = 0
    if do_plots:
        pdf = PdfPages(f'plots_direct/{plotname}_pdf.pdf')
    target_floor_price_list = []
    for ad_unit_name in ad_unit_names:
        df = df_all[df_all['ad_unit_name'] == ad_unit_name]
        df = df[df['fill_rate'] > 0]
        if len(df) == 0:
            continue

        df = df[df['requests'].cumsum() / df['requests'].sum() < ad_request_cum_prop_threshold]

        df[f'cpm_model'] = fit_model(df[['floor_price']], df['cpm'], True, 'request_limit', df)
        df[f'fill_rate_combined_exp_power_law'] = np.exp(fit_model(-pd.concat([np.log(df[['floor_price']]), df[['floor_price']]], axis=1), np.log(df['fill_rate']), True,'request_limit', df))
        df[f'fill_rate_exp_of_power_law'] = np.exp(-np.exp(fit_model(np.log(df[['floor_price']]), np.log(-np.log(df['fill_rate'])), True,'request_limit', df)))

        x1 = np.log(df['floor_price'].values)
        y = np.log(-np.log(df['fill_rate'].values))

        # X = np.matrix([[len(x1), x1.sum()], [x1.sum(), (x1 ** 2).sum()]])
        # Xy = np.matrix([[y.sum()], [(x1 * y).sum()]])
        # beta = np.linalg.inv(X) * Xy
        # target_floor_price = np.exp((np.log(-np.log(target_fill_rate)) - beta[0]) / beta[1])[0, 0]

        X11 = len(x1)
        X12 = x1.sum()
        X22 = (x1 ** 2).sum()
        # det = X11*X22 - X12*X12
        # Xinv11 = X22 / det
        # Xinv12 = -X12 / det
        # Xinv22 = X11 / det
        Xy1 = y.sum()
        Xy2 = (x1 * y).sum()
        # beta1 = (Xinv11 * Xy1) + (Xinv12 * Xy2)
        # beta2 = (Xinv12 * Xy1) + (Xinv22 * Xy2)
        # beta1 = (X22*Xy1 - X12*Xy2) / det # = ln(lambda)
        # beta2 = (X11*Xy2 - X12*Xy1) / det # = n
        # target_floor_price = np.exp((np.log(-np.log(target_fill_rate)) - beta1) / beta2)
        # target_floor_price = np.exp( (np.log(-np.log(target_fill_rate)) - beta1) / beta2 )
        # target_floor_price = np.exp(det * (np.log(-np.log(target_fill_rate)) - (X22*Xy1 - X12*Xy2)) / (X22*Xy1 - X12*Xy2))

        target_floor_price = np.exp( ((X11*X22 - X12*X12) * np.log(-np.log(target_fill_rate)) - (X22*Xy1 - X12*Xy2)) / (X11*Xy2 - X12*Xy1))

        #f = exp [ ( ln ( -ln ( fill_rate ) ) - ln ( lambda ) ) / n ]
        #reg = LinearRegression(fit_intercept=True, positive=False).fit(x1.reshape(-1, 1), y)

        df = df.set_index('floor_price')

        target_floor_price = {'cpma_weighted': calculate_target_floor_price(df, 100, 'cpma'),
                              'closed_form': target_floor_price}
        for model in ['combined_exp_power_law', 'exp_of_power_law']:
            df[f'cpma_{model}'] = df[f'fill_rate_{model}'] * df[f'cpm_model']
            target_floor_price[f'fill_rate_{model}'] = target_floor_price_from_fill_rate(df[f'fill_rate_{model}'], target_fill_rate)
            target_floor_price[f'cpma_{model}'] = df[f'cpma_{model}'].idxmax()

        target_floor_price_list.append(target_floor_price)

        if do_plots and (N_i < N):
            if N_p_i == 0:
                fig, ax = plt.subplots(figsize=(20, 16), ncols=3, nrows=N_p)

            cols = [c for c in df.columns if 'fill_rate' in c]
            df[cols].plot(ax=ax[N_p_i, 0])#, legend=None)
            fp = pd.concat([df_vert_line(v, 0, 1, f'{k}: {v:0.2f}') for k, v in target_floor_price.items()])
            fp.plot(ax=ax[N_p_i, 0], legend=None)

            cols = [c for c in df.columns if ('cpm' in c) and ('cpma' not in c)]
            df[cols].plot(ax=ax[N_p_i, 1])#, legend=None)

            cols = [c for c in df.columns if 'cpma' in c]
            df[cols].plot(ax=ax[N_p_i, 2])#, legend=None)
            fp = pd.concat([df_vert_line(v, 0, df[cols].max().max(), f'{k}: {v:0.2f}') for k, v in target_floor_price.items()])
            fp.plot(ax=ax[N_p_i, 2], legend=None)

            N_p_i += 1
            N_i += 1
            if N_p_i == N_p:
                fig.savefig(f'plots_direct/{plotname}_png_{NN_p}.png')
                pdf.savefig()
                NN_p += 1
                N_p_i = 0

    if do_plots:
        pdf.close()

    df_target_floor_price = pd.DataFrame(target_floor_price_list)
    df_target_floor_price.to_csv(f'plots_direct/{plotname}_target_floor_prices_{ad_unit_count}.csv', index=False)

    main_ad_unit_combined_model_v2_do_plots(f'{plotname}_target_floor_prices_{ad_unit_count}')

def cum_plot(df, filename):

    x_list = []
    for nm, x in df.items():
        x = x[np.isfinite(x)]
        x = x.sort_values()
        x_list.append(pd.DataFrame(np.arange(len(x)) / (len(x) - 1), index=pd.Index(x.values), columns=[nm]))

    df = pd.concat(x_list)
    df = df.groupby(df.index).mean()
    df = df.sort_index().ffill().bfill()

    fig, ax = plt.subplots(figsize=(12, 9))
    (100 * df).plot(xlim=[0, 2], ax=ax, ylabel='Cumulative percent of data_cache', xlabel='Target floor price',
                    title='CDF of target floor prices for different approaches')
    fig.savefig(f'plots_direct/{filename}.png')
    f = 0


def main_ad_unit_combined_model_v2_do_plots(filename):

    #main_ad_unit_compare_do_plots(filename, None, None)

    df = pd.read_csv(f'plots_direct/{filename}.csv')

    # df_fill_rate = df[['fill_rate_combined_exp_power_law', 'fill_rate_exp_of_power_law']]
    # filename_fill_rate = f'{filename}_fill_rate'
    # df_fill_rate.to_csv(f'plots_direct/{filename_fill_rate}.csv', index=False)
    # main_ad_unit_compare_do_plots(filename_fill_rate, None, None)

#    cum_plot(df[['cpma_weighted', 'fill_rate_combined_exp_power_law', 'fill_rate_exp_of_power_law']], f'{filename}_cum_plot')

    cum_plot(df, f'{filename}_cum_plot')

    g = 0





if __name__ == "__main__":
    #main_base()
    #main()

#    main_ad_unit_multiple()

#    main_ad_unit_multiple_price_pressure()

#    main_ad_unit_compare()

   #main_ad_unit_compare_do_plots()

    #main_ad_unit_compare_limit_fill_rate()

#    main_ad_unit_compare_limit_fill_rate_do_table()
#
#    main_ad_unit_cpm_model()

#    main_ad_unit_combined_model()

#    fill_rate_modelling_raw()

#    fill_rate_modelling()
#    fill_rate_modelling_selected()

    main_ad_unit_combined_model_v2()

#    main_ad_unit_combined_model_v2_do_plots('compare_combined_model_v2')


