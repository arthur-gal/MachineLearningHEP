#############################################################################
##  © Copyright CERN 2018. All rights not expressly granted are reserved.  ##
##                 Author: Gian.Michele.Innocenti@cern.ch                  ##
## This program is free software: you can redistribute it and/or modify it ##
##  under the terms of the GNU General Public License as published by the  ##
## Free Software Foundation, either version 3 of the License, or (at your  ##
## option) any later version. This program is distributed in the hope that ##
##  it will be useful, but WITHOUT ANY WARRANTY; without even the implied  ##
##     warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    ##
##           See the GNU General Public License for more details.          ##
##    You should have received a copy of the GNU General Public License    ##
##   along with this program. if not, see <https://www.gnu.org/licenses/>. ##
#############################################################################

import binascii
from io import BytesIO
from flask import Flask, render_template, request

from machine_learning_hep.general import get_database_ml_parameters, getdataframe
from machine_learning_hep.general import createstringselection
from machine_learning_hep.general import get_database_ml_gridsearch
from machine_learning_hep.functions import create_mlsamples, do_correlation
from machine_learning_hep.io import parse_yaml, checkdir
from machine_learning_hep.models import getclf_scikit, getclf_xgboost, getclf_keras
from machine_learning_hep.models import fit, savemodels, decisionboundaries
from machine_learning_hep.models import importanceplotall
from machine_learning_hep.mlperformance import cross_validation_mse, cross_validation_mse_continuous
from machine_learning_hep.mlperformance import plot_cross_validation_mse, plot_learning_curves
# from machine_learning_hep.mlperformance import confusion
from machine_learning_hep.mlperformance import precision_recall
from machine_learning_hep.grid_search import do_gridsearch, read_grid_dict, perform_plot_gridsearch

APP = Flask(__name__)


@APP.route('/')
# https://test-app-227515.appspot.com
def root():
    # For the sake of example, use static information to inflate the template.
    # This will be replaced with real information in later steps.
    return render_template('test.html')


@APP.route('/formSubmit', methods=['POST'])  # https://test-app-227515.appspot.com/
def post_form():  # pylint: disable=too-many-locals, too-many-statements

    mltype = "BinaryClassification"
    case = request.form['slct2']
    data = get_database_ml_parameters()
    filesig, filebkg = data[case]["sig_bkg_files"]
    trename = data[case]["tree_name"]
    var_all = data[case]["var_all"]
    var_signal = data[case]["var_signal"]
    sel_signal = data[case]["sel_signal"]
    sel_bkg = data[case]["sel_bkg"]
    var_training = data[case]["var_training"]
    var_corr_x, var_corr_y = data[case]["var_correlation"]

#     filedata, filemc = data[case]["data_mc_files"]
#     var_target = data[case]["var_target"]
#     var_boundaries = data[case]["var_boundaries"]

    filesig = "../"+filesig
    filebkg = "../"+filebkg
    var_skimming = ["pt_cand_ML"]
    varmin = [0]
    varmax = [10]
    rnd_shuffle = 12
    nevt_sig = 1000
    nevt_bkg = 1000
    test_frac = 0.2
    rnd_splt = 12
    plotdir = "./"
    nkfolds = 10
    ncores = 1

    activate_scikit = request.form.get('activate_scikit', type=bool)
    activate_xgboost = request.form.get('activate_xgboost', type=bool)
    activate_keras = request.form.get('activate_keras', type=bool)

    docorrelation = request.form.get('docorrelation', type=bool)
    dotraining = request.form.get('dotraining', type=bool)
    doROC = request.form.get('doROC', type=bool)
    dolearningcurve = request.form.get('dolearningcurve', type=bool)
    docrossvalidation = request.form.get('docrossvalidation', type=bool)
    doimportance = request.form.get('doimportance', type=bool)
    dogridsearch = request.form.get('dogridsearch', type=bool)

    string_selection = createstringselection(var_skimming, varmin, varmax)
    suffix = f"nevt_sig{nevt_sig}_nevt_bkg{nevt_bkg}_" \
             f"{mltype}{case}_{string_selection}"

    dataframe = f"dataframes_{suffix}"
    plotdir = f"plots_{suffix}"
    output = f"output_{suffix}"
    checkdir(dataframe)
    checkdir(plotdir)
    checkdir(output)

    classifiers = []
    classifiers_scikit = []
    classifiers_xgboost = []
    classifiers_keras = []

    names = []
    names_scikit = []
    names_xgboost = []
    names_keras = []

    trainedmodels = []

    df_sig = getdataframe(filesig, trename, var_all)
    df_bkg = getdataframe(filebkg, trename, var_all)
    # pylint: disable=unused-variable
    _, _, df_sig_train, df_bkg_train, _, _, x_train, y_train, x_test, y_test = \
        create_mlsamples(df_sig, df_bkg, sel_signal, sel_bkg, rnd_shuffle,
                         var_skimming, varmin, varmax, var_signal, var_training,
                         nevt_sig, nevt_bkg, test_frac, rnd_splt)

    if docorrelation:
        imageIO_vardist, imageIO_scatterplot, imageIO_corr_sig, imageIO_corr_bkg = \
        do_correlation(df_sig_train, df_bkg_train, var_all, var_corr_x, var_corr_y, plotdir)

    if activate_scikit:
        classifiers_scikit, names_scikit = getclf_scikit(mltype)
        classifiers = classifiers+classifiers_scikit
        names = names+names_scikit

    if activate_xgboost:
        classifiers_xgboost, names_xgboost = getclf_xgboost(mltype)
        classifiers = classifiers+classifiers_xgboost
        names = names+names_xgboost

    if activate_keras:
        classifiers_keras, names_keras = getclf_keras(mltype, len(x_train.columns))
        classifiers = classifiers+classifiers_keras
        names = names+names_keras

    if dotraining:
        trainedmodels = fit(names, classifiers, x_train, y_train)
        savemodels(names, trainedmodels, output, suffix)

    if doROC:
        imageIO_precision_recall, imageIO_ROC = \
            precision_recall(names, classifiers, suffix, x_train, y_train, nkfolds, plotdir)

    if docrossvalidation:
        df_scores = []
        if mltype == "Regression":
            df_scores = cross_validation_mse_continuous(
                names, classifiers, x_train, y_train, nkfolds, ncores)
        if mltype == "BinaryClassification":
            df_scores = cross_validation_mse(names, classifiers, x_train, y_train,
                                             nkfolds, ncores)
        img_scoresRME = plot_cross_validation_mse(names, df_scores, suffix, plotdir)


    if doimportance:
        img_import = importanceplotall(var_training, names_scikit+names_xgboost,
                                       classifiers_scikit+classifiers_xgboost, suffix, plotdir)

    if dolearningcurve:
        npoints = 10
        imageIO_plot_learning_curves = plot_learning_curves(
            names, classifiers, suffix, plotdir, x_train, y_train, npoints)

    if dogridsearch:
        datasearch = get_database_ml_gridsearch()
        analysisdb = datasearch[mltype]
        names_cv, clf_cv, par_grid_cv, refit_cv, var_param, \
            par_grid_cv_keys = read_grid_dict(analysisdb)
        _, _, dfscore = do_gridsearch(
            names_cv, clf_cv, par_grid_cv, refit_cv, x_train, y_train, nkfolds,
            ncores)
        img_gridsearch = perform_plot_gridsearch(
            names_cv, dfscore, par_grid_cv, par_grid_cv_keys, var_param, plotdir, suffix, 0.1)

    imageIO_vardist = binascii.b2a_base64(imageIO_vardist.read())
    imageIO_scatterplot = binascii.b2a_base64(imageIO_scatterplot.read())
    imageIO_corr_sig = binascii.b2a_base64(imageIO_corr_sig.read())
    imageIO_corr_bkg = binascii.b2a_base64(imageIO_corr_bkg.read())
    imageIO_precision_recall = binascii.b2a_base64(imageIO_precision_recall.read())
    imageIO_ROC = binascii.b2a_base64(imageIO_ROC.read())
    imageIO_plot_learning_curves = binascii.b2a_base64(imageIO_plot_learning_curves.read())
    img_scoresRME = binascii.b2a_base64(img_scoresRME.read())
    img_import = binascii.b2a_base64(img_import.read())
    img_gridsearch = binascii.b2a_base64(img_gridsearch.read())

    return render_template('display.html', \
             imageIO_vardist=imageIO_vardist.decode("utf-8"), \
             imageIO_scatterplot=imageIO_scatterplot.decode("utf-8"), \
             imageIO_corr_sig=imageIO_corr_sig.decode("utf-8"), \
             imageIO_corr_bkg=imageIO_corr_bkg.decode("utf-8"), \
             imageIO_precision_recall=imageIO_precision_recall.decode("utf-8"), \
             imageIO_ROC=imageIO_ROC.decode("utf-8"), \
             imageIO_plot_learning_curves=imageIO_plot_learning_curves.decode("utf-8"), \
             img_scoresRME=img_scoresRME.decode("utf-8"), \
             img_import=img_import.decode("utf-8"), \
             img_gridsearch=img_gridsearch.decode("utf-8"))


def main():
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.
    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    APP.run(host='127.0.0.1', port=8080, debug=True)