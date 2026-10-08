PREFIX = "park"
FOLDER_NAME = "scenarios"

TOTAL_POPULATION = 80
BAD_DRIVERS_PERCENTAGE = 0.5
INITIAL_WALLET = 100 # Base wallet for all vehicles
OUTER_POPULATION_PERCENTAGE = 0.05 # Percentage of vehicles which never park in out of town areas (e.g. tourists)
OUTER_POPULATION_SEED = 31 # Seed used to determine which vehicle belongs to the outer population
OUTER_POPULATION_WALLET_MULTIPLIER = 1.5
TOTAL_STOPS = 10
STOPS_PER_DAY = 5

MIN_PARK_DURATION = 1
MAX_PARK_DURATION = 24
STEPS_PER_HOUR = 100

PARK_AREA_NAMES = ["ParkArea", "ParkAreaAlternative", "ParkAreaOutOfTown"]

STARTING_STOP = 7  # Number of <param> tags before the first <stop> in each <trip>
STANDARD_AUCTION_PRICE = 2

MAX_REVIEW_STARS = 5
OVERSTAY_THRESHOLD = 3

CONSTANT_BUFFER_SPOTS = -1
INITIAL_BUFFER_SPOTS = 1
MAX_BUFFER_SPOTS = 3

BUFFER_STRATEGY = "incremental" # "legacy", "incremental", "weighted"

BUFFER_RISK_WEIGHT = 0.5 # Only works with weighted strategy. Should be between 0.0 and 1.0.

BUFFER_RESET_PERIOD = 8 * STEPS_PER_HOUR # Only works with legacy strategy. Specifies the number of steps after which the buffer dimension gets reset to INITIAL_BUFFER_SPOTS

BUFFER_WARMUP_STEPS = 0 # Only works with legacy strategy. Specifies the number of initial steps in which the buffer dimension is set to MAX_BUFFER_SPOTS


GOOD_OVERSTAY_PROBABILITY = 0.05 # Base probability for good vehicles to overstay
BAD_OVERSTAY_PROBABILITY = 0.60  # Base probability for bad vehicles to overstay

OVERSTAY_PROBABILITY_SPREAD = 0.0 # How much a vehicle is likely to overstay within its base probability
OVERSTAY_PROBABILITY_SEED = 72 # Seed used to determine the previous variable

RATING_DETERRENCE = 0.0 # Needed to adjust the overstay probabilities (see above) based on user's stars: 1 - RATING_DETERRENCE * <user_stars> / MAX_REVIEW_STARS

MIN_OVERSTAY_STEPS = STEPS_PER_HOUR // 4
MAX_OVERSTAY_STEPS = 2 * STEPS_PER_HOUR

BAD_LEARNING_PROBABILITY = 0.5 # Base probability of a vehicle to correct its behaviour after receiving a warning or losing a star
LEARNING_PROBABILITY_SPREAD = 0.0 # How much a vehicle is likely to correct its behaviour within its base probability
WARNING_LEARNING_RATE = 0.3 # How much the behaviour gets corrected after receiving a warning
STAR_LOSS_LEARNING_RATE = 0.5 # How much the behaviour gets corrected after losing a star

BAD_VEHICLE_TYPE = "carB" # Type of vehicle sporting a bad behavior, used by SUMO in its routes file

BEHAVIOUR_SEED = 27 # Vehicles behaviour random seed

TOTAL_PARK_AREAS = 8
DOUBLE_ROWS = 2
SLOTS_PER_ROW = 10
SLOT_LENGTH = 9
SLOT_WIDTH = 5


PARK_ROW_DISTANCE = 29