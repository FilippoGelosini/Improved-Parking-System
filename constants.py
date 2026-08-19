PREFIX = "park"
FOLDER_NAME = "scenarios"

TOTAL_POPULATION = 80
BAD_DRIVERS_PERCENTAGE = 0.5
TOTAL_STOPS = 10
STOPS_PER_DAY = 5

MIN_PARK_DURATION = 1
MAX_PARK_DURATION = 24
STEPS_PER_HOUR = 100

PARK_AREA_NAMES = ["ParkArea", "ParkAreaAlternative", "ParkAreaOutOfTown"]

STARTING_STOP = 6  # Number of <param> tags before the first <stop> in each <trip>
STANDARD_AUCTION_PRICE = 2

MAX_REVIEW_STARS = 5
OVERSTAY_THRESHOLD = 3

CONSTANT_BUFFER_SPOTS = -1
INITIAL_BUFFER_SPOTS = 1
MAX_BUFFER_SPOTS = 3

BUFFER_STRATEGY = "weighted" # "legacy", "incremental", "weighted"

BUFFER_RISK_WEIGHT = 0.5 # Only works with weighted strategy. Should be between 0.0 and 1.0.

BUFFER_RESET_PERIOD = 8 * STEPS_PER_HOUR # Only works with legacy strategy. Specifies the number of steps after which the buffer dimension gets reset to INITIAL_BUFFER_SPOTS

BUFFER_WARMUP_STEPS = 0 # Only works with legacy strategy. Specifies the number of initial steps in which the buffer dimension is set to MAX_BUFFER_SPOTS

TOTAL_PARK_AREAS = 8
DOUBLE_ROWS = 2
SLOTS_PER_ROW = 10
SLOT_LENGTH = 9
SLOT_WIDTH = 5


PARK_ROW_DISTANCE = 29