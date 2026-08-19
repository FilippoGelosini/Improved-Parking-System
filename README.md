# Improved parking system

Exploring different strategies for managing a dynamic buffer in a reservation based parking system

### Prerequisites:

- SUMO
- Python
- TraCI (Python library)
- Sumolib (Python library)
- lxml (Python library)

### Usage:

1. First, set the constants in `constants.py` to your desired values
2. Build the scenario: `python buildScenario.py [--routesonly]`  
Option `--routesonly` generates **ONLY** the routes file
3. Choose the desired buffer management strategy by editing the constant `BUFFER_STRATEGY` in `constants.py`
4. Run the simulation: `python runner.py [--nogui]`  
Option `--nogui` will run the command line version of SUMO

By default, `runner.py` loads the scenario that "matches" the total population number specified in `TOTAL_POPULATION`, e.g. `TOTAL_POPULATION = 80` loads `scenarios/park_80`. Can be edited if needed. I'll probably move the string containing the path to the scenario to `constants.py`