class Config():
    def __init__(self, config):
        self.columns = config['columns']
        self.relevantColumns = config['relevantColumns']
        self.labelNames = config['labelNames']
        self.columnUnits = config['columnUnits']
        self.timestamps = config['timestamps']


def getConfigs():
    return {
        'furnace_A': getConfigFurnaceA,
        'furnace_B': getConfigFurnaceB,
    }


def getConfigDirs():
    return getConfigs().keys()


def getConfig(name):
    configs = getConfigs()
    if name in getConfigDirs():
        return configs[name]()
    else:
        return [None, None, None, None, None]


def getConfigFurnaceA():
    columnDescriptions = {
        'fuel_flow': 'Fuel flow rate',
        'air_flow_primary': 'Primary air flow rate',
        'air_flow_secondary': 'Secondary air flow rate',
        'feed_temp': 'Feed inlet temperature',
        'feed_flow': 'Feed flow rate',
        'flue_gas_temp': 'Flue gas temperature',
        'tube_wall_temp_1': 'Tube wall temperature zone 1',
        'tube_wall_temp_2': 'Tube wall temperature zone 2',
        'tube_wall_temp_3': 'Tube wall temperature zone 3',
        'outlet_temp': 'Furnace outlet temperature',
        'stack_temp': 'Stack temperature',
        'o2_flue': 'Flue gas O2 concentration',
        'co_flue': 'Flue gas CO concentration',
        'draft_pressure': 'Furnace draft pressure',
        'efficiency': 'Furnace thermal efficiency',
    }

    columnUnits = {
        'fuel_flow': 'kg/h',
        'air_flow_primary': 'kg/h',
        'air_flow_secondary': 'kg/h',
        'feed_temp': '°C',
        'feed_flow': 'kg/h',
        'flue_gas_temp': '°C',
        'tube_wall_temp_1': '°C',
        'tube_wall_temp_2': '°C',
        'tube_wall_temp_3': '°C',
        'outlet_temp': '°C',
        'stack_temp': '°C',
        'o2_flue': '%',
        'co_flue': 'ppm',
        'draft_pressure': 'mmH2O',
        'efficiency': '%',
    }

    columns = [
        ['fuel_flow', 'Fuel flow rate', 'kg/h'],
        ['air_flow_primary', 'Primary air flow rate', 'kg/h'],
        ['air_flow_secondary', 'Secondary air flow rate', 'kg/h'],
        ['feed_temp', 'Feed inlet temperature', '°C'],
        ['feed_flow', 'Feed flow rate', 'kg/h'],
        ['flue_gas_temp', 'Flue gas temperature', '°C'],
        ['tube_wall_temp_1', 'Tube wall temperature zone 1', '°C'],
        ['tube_wall_temp_2', 'Tube wall temperature zone 2', '°C'],
        ['tube_wall_temp_3', 'Tube wall temperature zone 3', '°C'],
        ['outlet_temp', 'Furnace outlet temperature', '°C'],
        ['stack_temp', 'Stack temperature', '°C'],
        ['o2_flue', 'Flue gas O2 concentration', '%'],
        ['co_flue', 'Flue gas CO concentration', 'ppm'],
        ['draft_pressure', 'Furnace draft pressure', 'mmH2O'],
        ['efficiency', 'Furnace thermal efficiency', '%'],
    ]

    relevantColumns = [col[0] for col in columns]

    return Config({
        'columns': columns,
        'relevantColumns': relevantColumns,
        'labelNames': columnDescriptions,
        'columnUnits': columnUnits,
        'timestamps': None,
    })


def getConfigFurnaceB():
    columnDescriptions = {
        'fuel_flow': 'Fuel flow rate',
        'air_flow': 'Total air flow rate',
        'feed_temp': 'Feed inlet temperature',
        'feed_flow': 'Feed flow rate',
        'flue_gas_temp': 'Flue gas temperature',
        'outlet_temp': 'Furnace outlet temperature',
        'stack_temp': 'Stack temperature',
        'o2_flue': 'Flue gas O2 concentration',
        'efficiency': 'Furnace thermal efficiency',
    }

    columnUnits = {
        'fuel_flow': 'kg/h',
        'air_flow': 'kg/h',
        'feed_temp': '°C',
        'feed_flow': 'kg/h',
        'flue_gas_temp': '°C',
        'outlet_temp': '°C',
        'stack_temp': '°C',
        'o2_flue': '%',
        'efficiency': '%',
    }

    columns = [
        ['fuel_flow', 'Fuel flow rate', 'kg/h'],
        ['air_flow', 'Total air flow rate', 'kg/h'],
        ['feed_temp', 'Feed inlet temperature', '°C'],
        ['feed_flow', 'Feed flow rate', 'kg/h'],
        ['flue_gas_temp', 'Flue gas temperature', '°C'],
        ['outlet_temp', 'Furnace outlet temperature', '°C'],
        ['stack_temp', 'Stack temperature', '°C'],
        ['o2_flue', 'Flue gas O2 concentration', '%'],
        ['efficiency', 'Furnace thermal efficiency', '%'],
    ]

    relevantColumns = [col[0] for col in columns]

    return Config({
        'columns': columns,
        'relevantColumns': relevantColumns,
        'labelNames': columnDescriptions,
        'columnUnits': columnUnits,
        'timestamps': None,
    })
