import sys
import os

ROOT_PATH = os.path.abspath(".").split("src")[0]
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)
module_path = os.path.abspath(os.path.join(ROOT_PATH + "/src/utils/"))
if module_path not in sys.path:
    sys.path.append(module_path)

from configs import getConfig

import core


def loadFurnaceConfig(configName):
    """
    Load a predefined furnace configuration and return the config object.

    PARAMS:
        configName: str - name of the furnace config (e.g., 'furnace_A', 'furnace_B')

    RETURNS:
        config: Config object with columns, relevantColumns, labelNames, columnUnits, timestamps
    """
    config = getConfig(configName)
    return config


def initFurnaceDataframe(filename, configName, irrelevantColumns=None):
    """
    Initialize a dataframe using a predefined furnace configuration.

    PARAMS:
        filename: str - path to the data file
        configName: str - name of the furnace config
        irrelevantColumns: list of str - columns to exclude (optional)

    RETURNS:
        df: Pandas DataFrame
        config: Config object
    """
    config = loadFurnaceConfig(configName)

    if irrelevantColumns is None:
        irrelevantColumns = []

    df = core.initDataframe(filename, config.columns, irrelevantColumns)

    return df, config
