import traci

from constants import (
    MAX_BUFFER_SPOTS,
    INITIAL_BUFFER_SPOTS,
    OVERSTAY_THRESHOLD,
    BUFFER_STRATEGY,
    BUFFER_RISK_WEIGHT,
    BUFFER_RESET_PERIOD,
    BUFFER_WARMUP_STEPS,
    MAX_REVIEW_STARS,
)


class LegacyBufferManager:
    """Previous buffer management strategy"""

    def __init__(
        self,
        max_buffer: int = MAX_BUFFER_SPOTS,
        reset_period: int = BUFFER_RESET_PERIOD,
        warmup_steps: int = BUFFER_WARMUP_STEPS,
        initial_buffer: int = INITIAL_BUFFER_SPOTS
    ):
        self.max_buffer = max_buffer
        self.reset_period = reset_period
        self.warmup_steps = warmup_steps
        self.initial_buffer = initial_buffer

        # Indicates the buffer dimension for each area. Accessed via the property "free_parks", which updates the clock first
        self._free_parks = {}

        # Index of the last observed buffer refresh period (see "BUFFER_RESET_PERIOD" in constants.py). Increments only when BUFFER_RESET_PERIOD simulation steps passed.
        self._period = 0

    # Private methods -------------------------------------------------------------

    def _refresh(self) -> float:
        """Resets the buffers if needed, returns the current simulation step"""
        now = traci.simulation.getTime()
        if self.reset_period > 0:
            period = now // self.reset_period
            if period != self._period:
                self._period = period
                self._free_parks = dict.fromkeys(
                    self._free_parks, self.initial_buffer
                )
        return now

    # Public methods --------------------------------------------------------------

    def get_buffer(self, park_area: str, default_initial: int) -> int:
        """Returns the current buffer dimension. If the area buffer is not initialized yet returns the default initial buffer spots"""
        now = self._refresh()
        if now < self.warmup_steps:
            return self.max_buffer
        return self._free_parks.get(park_area, default_initial)

    # Management hooks ------------------------------------------------------------

    def on_reservation(self, id_vehicle: str, park_area: str, initial_buffer: int):
        """No action on new reservations"""

    def on_overstay_start(self, id_vehicle: str, park_area: str, initial_buffer: int):
        """No action when an overstay is detected"""

    def on_exit(self, id_vehicle: str, park_area: str, overstayed: bool):
        """If the user overstayed, the buffer's dimension for the given area increments if < self.max_buffer"""
        self._refresh()
        if not overstayed:
            return

        self._free_parks[park_area] = min(
            self.max_buffer, self._free_parks.get(park_area, self.initial_buffer) + 1
        )

    # Getters ---------------------------------------------------------------------

    @property
    def free_parks(self) -> dict:
        """Calls self._refresh() and returns self._free_parks"""
        self._refresh()
        return self._free_parks


class IncrementalBufferManager:
    """Evolution of the legacy buffer management, aims to be more reactive"""

    def __init__(
        self,
        overstay_threshold: int = OVERSTAY_THRESHOLD,
        max_buffer: int = MAX_BUFFER_SPOTS
    ):
        self.n = overstay_threshold
        self.max_buffer = max_buffer

        # Counts consecutive overstays for each vehicle
        self.user_consecutive_overstays = {}

        # Indicates the area in which a vehicle made an overstay, and therefore incrementes the buffer size. Used to know if and where to decrement the buffer when a vehicle exits the area. Vehicles are the dict keys, park area names are the values, e.g. {"v27": "ParkArea0", "v3": None} 
        self.user_buffer_added = {}

        # Indicates the buffer dimension for each area.
        self.free_parks = {}

    # Private methods -------------------------------------------------------------

    def _init_area_if_needed(self, park_area: str, initial_buffer: int):
        """Initializes the buffer for a given area if said area is not in self.free_parks"""
        if park_area not in self.free_parks:
            self.free_parks[park_area] = initial_buffer

    def _increment_buffer(self, park_area: str) -> bool:
        """Increments buffer's dimension if < self.max_buffer, returns True if the dimension was increased, False otherwise"""
        if self.free_parks[park_area] < self.max_buffer:
            self.free_parks[park_area] += 1
            return True

        return False

    def _release_spot(self, id_vehicle: str):
        """Releases the buffer spot increase caused by the given vehicle"""
        # If the given vehicle caused a buffer dimension increase, the area in which the increase happened gets retrieved from 'self.user_buffer_added': If the returned value is None, the given vehicle did NOT cause a buffer dimension increase, even if it overstayed/has a bad reputation, therefore no decrease is needed.
        buffered_area = self.user_buffer_added.get(id_vehicle)
        if buffered_area is None:
            return

        # Instead, if the returned value is not None, the vehicle did cause an increase, and the name of the area in which the increase happened is the returned value. The dimension gets decreased and the value relative to the key (vehicle) in 'self.user_buffer_added' gets set to None 
        self.free_parks[buffered_area] = max(
            0, self.free_parks[buffered_area] - 1
        )
        
        self.user_buffer_added[id_vehicle] = None
    
    # Public methods --------------------------------------------------------------

    def get_buffer(self, park_area: str, default_initial: int) -> int:
        """Returns the current buffer dimension. If the area buffer is not initialized yet returns the default initial buffer spots"""
        return self.free_parks.get(park_area, default_initial)

    def get_user_overstays(self, id_vehicle: str) -> int:
        """Returns the number of consecutive overstays for a given vehicle"""
        return self.user_consecutive_overstays.get(id_vehicle, 0)

    # Management hooks ------------------------------------------------------------

    def on_reservation(self, id_vehicle: str, park_area: str, initial_buffer: int):
        """If a "bad" vehicle makes a reservation, the buffer dimension automatically tries to increase"""
        self._release_spot(id_vehicle) # Only useful if the given vehicle has been redirected to a new area, this way the buffer releases the eventual increase caused by the original area reservation
        self._init_area_if_needed(park_area, initial_buffer)
        overstays = self.user_consecutive_overstays.get(id_vehicle, 0)

        if overstays >= self.n:
            # The given vehicle has a bad reputation: we try to increase the buffer dimension as soon as the reservation happens. If the buffer dimension is actually increased, the affected area gets stored
            self.user_buffer_added[id_vehicle] = (
                park_area if self._increment_buffer(park_area) else None
            )

    def on_overstay_start(self, id_vehicle: str, park_area: str, initial_buffer: int):
        """If an overstay is detected, and the vehicle did not already trigger a buffer dimension increase during the reservation, the buffer dimension tries to increase"""
        self._init_area_if_needed(park_area, initial_buffer)
        overstays = self.user_consecutive_overstays.get(id_vehicle, 0)

        if overstays < self.n:
            # First scenario, the vehicle did not trigger a buffer dimension increase during the reservation: we try to increase the buffer dimension as soon as the overstay is detected. If the buffer dimension is actually increased, the affected area gets stored
            self.user_buffer_added[id_vehicle] = (
                park_area if self._increment_buffer(park_area) else None
            )
        # Second scenario, the buffer dimension was already (supposedly) increased

        # The consecutive overstay counter gets updated anyways
        self.user_consecutive_overstays[id_vehicle] = overstays + 1

    def on_exit(self, id_vehicle: str, park_area: str, overstayed: bool):
        """If a vehicle who overstayed leaves, and it caused a buffer increase, the buffer dimension gets decreased. If a vehicle left the area and did NOT overstay, its consecutive overstay counter gets reset"""

        if not overstayed:
            self.user_consecutive_overstays[id_vehicle] = 0

        self._release_spot(id_vehicle)


def stars_in_area(park_area: str) -> list:
    """Returns a list containing the stars of the users parked in a given park area"""
    return [
        int(traci.vehicle.getParameter(id_vehicle, "reviewStars"))
        for id_vehicle in traci.parkingarea.getVehicleIDs(park_area)
    ]


class WeightedBufferManager:
    """Different strategy, the buffer dimension is calculated as a weighted average of the stars of alla vehicles ina given area"""

    def __init__(
        self,
        max_buffer: int = MAX_BUFFER_SPOTS,
        max_stars: int = MAX_REVIEW_STARS,
        risk_weight: float = BUFFER_RISK_WEIGHT
    ):
        self.max_buffer = max_buffer
        self.max_stars = max_stars
        self.risk_weight = risk_weight

        # Stores the park areas "seen" at least once, only used in the final output log
        self._areas = set()
        self._default_initial = INITIAL_BUFFER_SPOTS

    # Public methods --------------------------------------------------------------

    def get_buffer(self, park_area: str, default_initial: int) -> int:
        """Calculates the current buffer dimension for the given area and returns it"""
        self._areas.add(park_area)

        stars = list(stars_in_area(park_area))
        if not stars:
            return default_initial

        total_weight = 0.0
        weighted_risk = 0.0
        for star in stars:
            missing_stars = self.max_stars - star           # Reverses the stars scale
            risk = missing_stars / self.max_stars           # Normalized value
            weight = 1.0 + self.risk_weight * missing_stars # Lower score users weigh more on the average. 1.0 is added to the formula so that "total_weight" will never be 0 (in case of perfect users)
            weighted_risk += weight * risk                  # Total weight based on individual vehicle's risk of overstaying
            total_weight += weight                          # Total weight in the area

        mean_risk = weighted_risk / total_weight
        # int(x + 0.5) e non round(): round() in Python arrotonda 0.5 al pari
        # piu' vicino (0.5 -> 0), qui invece mezzo posto atteso va coperto.
        expected_overstays = int(mean_risk * len(stars) + 0.5) # + 0.5 needed to round to the closest integer
        return min(self.max_buffer, expected_overstays)

    # Management hooks ------------------------------------------------------------

    def on_reservation(self, id_vehicle: str, park_area: str, initial_buffer: int):
        """No action required when a vehicle reserves a spot"""

    def on_overstay_start(self, id_vehicle: str, park_area: str, initial_buffer: int):
        """No action required when a vehicle overstays"""

    def on_exit(self, id_vehicle: str, park_area: str, overstayed: bool):
        """No action required when a vehicle exits a park area"""

    # Getters ---------------------------------------------------------------------

    @property
    def free_parks(self) -> dict:
        """Buffer corrente di tutte le aree viste (per la stampa finale)."""
        return {
            area: self.get_buffer(area, self._default_initial)
            for area in sorted(self._areas)
        }

# Alias for the various strategies
BufferStrategy = LegacyBufferManager | IncrementalBufferManager | WeightedBufferManager

def make_buffer_manager(strategy: str = BUFFER_STRATEGY) -> BufferStrategy:
    """Builds the buffer manager specified in constants.py. Can raise a ValueError exception if the strategy is invalid"""
    if strategy == "legacy":
        return LegacyBufferManager(
            max_buffer=MAX_BUFFER_SPOTS,
            reset_period=BUFFER_RESET_PERIOD,
            warmup_steps=BUFFER_WARMUP_STEPS,
        )
    if strategy == "incremental":
        return IncrementalBufferManager(
            overstay_threshold=OVERSTAY_THRESHOLD, max_buffer=MAX_BUFFER_SPOTS
        )
    if strategy == "weighted":
        return WeightedBufferManager(
            max_buffer=MAX_BUFFER_SPOTS, risk_weight=BUFFER_RISK_WEIGHT
        )
    raise ValueError(
        f"Unknown value in constants.BUFFER_STRATEGY: {strategy!r}"
        ' (Acceptable values: "legacy", "incremental", "weighted")'
    )