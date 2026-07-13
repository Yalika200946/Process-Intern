HX_CONFIG = {
    'E101AB': {
        'title': 'E101AB - Crude vs 1st Side Run',
        'cold': [
            ('1FI007.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI102.pv',  'Crude Inlet Temp',    'DEGC'),
            ('1TI101.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1FI010.pv',  '1SR Inlet Flow',      'M3/HR'),
            ('1TI194.pv',  '1SR Inlet Temp',      'DEGC'),
            ('1TI103.pv',  '1SR Outlet Temp',     'DEGC'),
        ],
    },
    'E101CD': {
        'title': 'E101CD - Crude vs 1st Side Run',
        'cold': [
            ('1FI008.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI102.pv',  'Crude Inlet Temp',    'DEGC'),
            ('1TI104.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1FI011.pv',  '1SR Inlet Flow',      'M3/HR'),
            ('1TI194.pv',  '1SR Inlet Temp',      'DEGC'),
            ('1TI105.pv',  '1SR Outlet Temp',     'DEGC'),
        ],
    },
    'E101EF': {
        'title': 'E101EF - Crude vs 1st Side Run',
        'cold': [
            ('1FI009.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI102.pv',  'Crude Inlet Temp',    'DEGC'),
            ('1TI109.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1FI012.pv',  '1SR Inlet Flow',      'M3/HR'),
            ('1TI194.pv',  '1SR Inlet Temp',      'DEGC'),
            ('1TI110.pv',  '1SR Outlet Temp',     'DEGC'),
        ],
    },
    'E102': {
        'title': 'E102 - Crude vs Kerosene',
        'cold': [
            ('1TI107.pv',  'Crude Inlet Temp',    'DEGC'),
            ('1TI106.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1TI165.pv',  'Kero Inlet Temp',     'DEGC'),
            ('1TI108.pv',  'Kero Outlet Temp',    'DEGC'),
            ('1FC055.pv',  'Kero Outlet Flow',    'M3/HR'),
        ],
    },
    'E103AB': {
        'title': 'E103AB - Crude vs 2nd Side Run (2RS-1)',
        'cold': [
            ('1FI015.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI225.pv',  'Crude Inlet Temp',    'DEGC'),
            ('1TI136.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1FI018.pv',  '2RS-1 Inlet Flow',    'M3/HR'),
            ('4TI107.pv',  '2RS Inlet Temp',      'DEGC'),
            ('1TI137.pv',  '2RS-1 Outlet Temp',   'DEGC'),
        ],
    },
    'E104': {
        'title': 'E104 - Crude vs 2nd Side Run',
        'cold': [
            ('1FI015.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI136.pv',  'Crude Inlet Temp (from E103)',  'DEGC'),
            ('1TI112.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1TI195.pv',  '2RS Inlet Temp',      'DEGC'),
            ('4TI115.pv',  '2RS Outlet Temp',     'DEGC'),
        ],
    },
    'E105AB': {
        'title': 'E105AB - Crude vs 3rd Side Run',
        'cold': [
            ('1FI015.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI112.pv',  'Crude Inlet Temp (from E104)',  'DEGC'),
            ('1TI114.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1FC035.pv',  '3RS Flow',            'M3/HR'),
            ('1TI195.pv',  '3RS Inlet Temp',      'DEGC'),
            ('1TI113.pv',  '3RS Outlet Temp',     'DEGC'),
        ],
    },
    'E106AB': {
        'title': 'E106AB - Crude vs 2nd Side Run (2RS-2)',
        'cold': [
            ('1FI016.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI225.pv',  'Crude Inlet Temp',    'DEGC'),
            ('1TI128.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1FI019.pv',  '2RS-2 Inlet Flow',    'M3/HR'),
            ('4TI107.pv',  '2RS Inlet Temp',      'DEGC'),
            ('1TI129.pv',  '2RS-2 Outlet Temp',   'DEGC'),
        ],
    },
    'E107AB': {
        'title': 'E107AB - Crude vs Gas Oil',
        'cold': [
            ('1FI016.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI128.pv',  'Crude Inlet Temp (from E106)',  'DEGC'),
            ('1TI130.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1TI135.pv',  'GO Inlet Temp (from E109)',  'DEGC'),
            ('1TI131.pv',  'GO Outlet Temp',      'DEGC'),
        ],
    },
    'E108AB': {
        'title': 'E108AB - Crude vs Residue',
        'cold': [
            ('1FI016.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI130.pv',  'Crude Inlet Temp (from E107)',  'DEGC'),
            ('1TI132.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('439FI003.pv','Residue Flow',         'M3/HR'),
            ('1TI127.pv',  'Residue Inlet Temp',  'DEGC'),
            ('1TI133.pv',  'Residue Outlet Temp', 'DEGC'),
        ],
    },
    'E109AB': {
        'title': 'E109AB - Crude vs Gas Oil',
        'cold': [
            ('1FI016.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI132.pv',  'Crude Inlet Temp (from E108)',  'DEGC'),
            ('1TI134.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1TI163.pv',  'GO Inlet Temp',       'DEGC'),
            ('1TI135.pv',  'GO Outlet Temp',      'DEGC'),
        ],
    },
    'E110ABC': {
        'title': 'E110ABC - Crude vs Residue',
        'cold': [
            ('1FI017.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI225.pv',  'Crude Inlet Temp',    'DEGC'),
            ('1TI124.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('439FI003.pv','Residue Flow',         'M3/HR'),
            ('1TI133.pv',  'Residue Inlet Temp',  'DEGC'),
            ('1TI122.pv',  'Residue Outlet Temp', 'DEGC'),
        ],
    },
    'E111': {
        'title': 'E111 - Crude vs 3rd Side Run',
        'cold': [
            ('1FI017.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI124.pv',  'Crude Inlet Temp (from E110)',  'DEGC'),
            ('1TI123.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('1FC035.pv',  '3RS Flow',            'M3/HR'),
            ('1TI113.pv',  '3RS Inlet Temp (from E105)',  'DEGC'),
            ('1TI125.pv',  '3RS Outlet Temp',     'DEGC'),
        ],
    },
    'E112AB': {
        'title': 'E112AB - Crude vs Residue',
        'cold': [
            ('1FI017.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI123.pv',  'Crude Inlet Temp (from E111)',  'DEGC'),
            ('1TI126.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('439FI003.pv','Residue Flow',         'M3/HR'),
            ('1TI117.pv',  'Residue Inlet Temp',  'DEGC'),
            ('1TI127.pv',  'Residue Outlet Temp', 'DEGC'),
        ],
    },
    'E112C': {
        'title': 'E112C - Crude vs Residue',
        'cold': [
            ('1FI017.pv',  'Crude Inlet Flow',    'M3/HR'),
            ('1TI123.pv',  'Crude Inlet Temp (from E111)',  'DEGC'),
            ('1TI114.pv',  'Crude Outlet Temp',   'DEGC'),
        ],
        'hot': [
            ('439FI003.pv','Residue Flow',         'M3/HR'),
            ('1TI117.pv',  'Residue Inlet Temp',  'DEGC'),
            ('1TI117B.pv', 'Residue Outlet Temp', 'DEGC'),
        ],
    },
    'E113A': {
        'title': 'E113A - Crude vs Residue (last HX before Furnace)',
        'cold': [
            ('1TI115.pv',  'Crude Inlet Temp',    'DEGC'),
            ('1TI116.pv',  'Crude Outlet Temp (CIT)',  'DEGC'),
            ('1PI003.pv',  'Pressure Inlet Furnace',   'BARG'),
        ],
        'hot': [
            ('439FI003.pv','Residue Flow',         'M3/HR'),
            ('1TI161.pv',  'Residue from Distillation','DEGC'),
            ('1TI117.pv',  'Residue Outlet Temp',  'DEGC'),
            ('1PI055.pv',  'Residue Inlet Pressure','BARG'),
            ('1PI056.pv',  'Residue Outlet Pressure','BARG'),
        ],
    },
}
