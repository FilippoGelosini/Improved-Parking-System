import traci

from constants import (
    STEPS_PER_CALENDAR_SLOT,
    MAX_BUFFER_SPOTS,
    INITIAL_BUFFER_SPOTS,
    OVERSTAY_THRESHOLD,
    BUFFER_STRATEGY,
    BUFFER_RISK_WEIGHT,
    BUFFER_RESET_PERIOD,
    BUFFER_WARMUP_STEPS,
    MAX_REVIEW_STARS,
)

from vehicle import get_review_stars
from parkArea import get_park_area


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

        # Indicates the buffer dimension for each area.
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

    def get_buffer(self, park_area: str, time_slot: int) -> int:
        """Returns the current buffer dimension. If the area buffer is not initialized yet returns the default initial buffer spots"""
        time_slot_start = time_slot * STEPS_PER_CALENDAR_SLOT
        # Aggiorna l'azzeramento (e quindi self._period) prima di confrontare.
        self._refresh()
        if time_slot_start < self.warmup_steps:
            return self.max_buffer
        elif self.reset_period > 0 and time_slot_start // self.reset_period > self._period:
            return self.initial_buffer
        return self._free_parks.get(park_area, self.initial_buffer)

    # Management hooks ------------------------------------------------------------

    def on_reservation(self, id_vehicle: str, park_area: str, first_slot: int, last_slot: int):
        """No action on new reservations"""

    def on_cancel(self, id_vehicle: str, park_area: str, first_slot: int, last_slot: int):
        """No action when removing a reservation"""

    def on_overstay_start(self, id_vehicle: str, park_area: str, time_slot: int):
        """No action when an overstay is detected"""

    def on_exit(self, id_vehicle: str, park_area: str, overstayed: bool, time_slot: int):
        """If the user overstayed, the buffer's dimension for the given area increments if < self.max_buffer"""
        self._refresh()
        if not overstayed:
            return

        self._free_parks[park_area] = min(
            self.max_buffer, self._free_parks.get(park_area, self.initial_buffer) + 1
        )

    # Getters ---------------------------------------------------------------------

    def free_parks(self, time_slot: int) -> dict:
        """Buffer dimension of all park areas during the specified time slot"""
        self._refresh()
        return self._free_parks


class IncrementalBufferManager:
    """Evolution of the legacy buffer management, aims to be more reactive"""

    def __init__(
        self,
        overstay_threshold: int = OVERSTAY_THRESHOLD,
        max_buffer: int = MAX_BUFFER_SPOTS,
        initial_buffer: int = INITIAL_BUFFER_SPOTS
    ):
        self.n = overstay_threshold
        self.max_buffer = max_buffer
        self.initial_buffer = initial_buffer

        # Counts consecutive overstays for each vehicle
        self.user_consecutive_overstays = {}

        # Active requests for one extra buffer spot, one per (vehicle, area) pair:
        # {(id_vehicle, park_area): time slot from which the request counts}.
        # A request is added when a repeat offender books (from its first booked
        # slot, see on_reservation) or when an overstay is detected (from that slot,
        # see on_overstay_start), and it is removed when the vehicle leaves the area
        # (on_exit) or cancels its booking there (on_cancel). get_buffer counts the
        # requests already active in the given slot, capped at max_buffer.
        # E.g. {("v5", "ParkArea0"): 412, ("v12", "-ParkAreaAlternative1"): 430} 
        self.requests = {}

        self._areas = set()

    # Private methods -------------------------------------------------------------
    
    # Public methods --------------------------------------------------------------

    def get_buffer(self, park_area: str, time_slot: int) -> int:
        """Returns the current buffer dimension. If the area buffer is not initialized yet returns the default initial buffer spots"""
        self._areas.add(park_area)
        active_reservations = sum(
            1 for (vehicle, area), slot in self.requests.items() if area == park_area and slot <= time_slot
        )
        return min(self.max_buffer, self.initial_buffer + active_reservations)

    def get_user_overstays(self, id_vehicle: str) -> int:
        """Returns the number of consecutive overstays for a given vehicle"""
        return self.user_consecutive_overstays.get(id_vehicle, 0)

    def free_parks(self, time_slot: int) -> dict:
        """Buffer dimension of all park areas during the specified time slot"""
        return {
            area: self.get_buffer(area, time_slot)
            for area in sorted(self._areas)
        }

    # Management hooks ------------------------------------------------------------

    def on_reservation(self, id_vehicle: str, park_area: str, first_slot: int, last_slot: int):
        """If a "bad" vehicle makes a reservation, the buffer dimension automatically tries to increase"""
        overstays = self.user_consecutive_overstays.get(id_vehicle, 0)

        if overstays >= self.n or get_review_stars(id_vehicle) < 3:
            # The given vehicle has a bad reputation: we try to increase the buffer dimension as soon as the reservation happens. If the buffer dimension is actually increased, the affected area gets stored
            self.requests[(id_vehicle, park_area)] = first_slot

    def on_cancel(self, id_vehicle: str, park_area: str, first_slot: int, last_slot: int):
        """If a vehicle deletes its reservation in the specified area (redirection, anticipated exit), if it has a request (-> occupies/should occupy a buffer spot) it gets removed
        """
        self.requests.pop((id_vehicle, park_area), None)

    def on_overstay_start(self, id_vehicle: str, park_area: str, time_slot: int):
        """If an overstay is detected, and the vehicle did not already trigger a buffer dimension increase during the reservation, the buffer dimension tries to increase"""
        overstays = self.user_consecutive_overstays.get(id_vehicle, 0)

        if (id_vehicle, park_area) not in self.requests:
            # First scenario, the vehicle did not trigger a buffer dimension increase during the reservation: we try to increase the buffer dimension as soon as the overstay is detected. If the buffer dimension is actually increased, the affected area gets stored
            self.requests[(id_vehicle, park_area)] = time_slot
        # Second scenario, the buffer dimension was already (supposedly) increased

        # The consecutive overstay counter gets updated anyways
        self.user_consecutive_overstays[id_vehicle] = overstays + 1

    def on_exit(self, id_vehicle: str, park_area: str, overstayed: bool, time_slot: int):
        """If a vehicle who overstayed leaves, and it caused a buffer increase, the buffer dimension gets decreased. If a vehicle left the area and did NOT overstay, its consecutive overstay counter gets reset"""

        if not overstayed:
            self.user_consecutive_overstays[id_vehicle] = 0

        self.requests.pop((id_vehicle, park_area), None)


class WeightedBufferManager:
    """Different strategy, the buffer dimension is calculated as a weighted average of the stars of alla vehicles ina given area"""

    def __init__(
        self,
        stars_booked,
        max_buffer: int = MAX_BUFFER_SPOTS,
        max_stars: int = MAX_REVIEW_STARS,
        risk_weight: float = BUFFER_RISK_WEIGHT
    ):
        self.stars_booked = stars_booked
        self.max_buffer = max_buffer
        self.max_stars = max_stars
        self.risk_weight = risk_weight

        # Stores the park areas "seen" at least once, only used in the final output log
        self._areas = set()
        self._default_initial = INITIAL_BUFFER_SPOTS

    # Public methods --------------------------------------------------------------

    def get_buffer(self, park_area: str, time_slot: int) -> int:
        """Calculates the current buffer dimension for the given area and returns it"""
        self._areas.add(park_area)

        stars = list(self.stars_booked(park_area, time_slot))
        if not stars:
            return self._default_initial

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

    def free_parks(self, time_slot: int) -> dict:
        """Buffer dimension of all park areas during the specified time slot"""
        return {
            area: self.get_buffer(area, time_slot)
            for area in sorted(self._areas)
        }
    
    # Management hooks ------------------------------------------------------------

    def on_reservation(self, id_vehicle: str, park_area: str, first_slot: int, last_slot: int):
        """No action required when a vehicle reserves a spot"""

    def on_cancel(self, id_vehicle: str, park_area: str, first_slot: int, last_slot: int):
        """No action when removing a reservation"""

    def on_overstay_start(self, id_vehicle: str, park_area: str, time_slot: int):
        """No action required when a vehicle overstays"""

    def on_exit(self, id_vehicle: str, park_area: str, overstayed: bool, time_slot):
        """No action required when a vehicle exits a park area"""

    # Getters ---------------------------------------------------------------------


# Alias for the various strategies
BufferStrategy = LegacyBufferManager | IncrementalBufferManager | WeightedBufferManager

def make_buffer_manager(areas: dict, strategy: str = BUFFER_STRATEGY) -> BufferStrategy:
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
        # Function "stars_booked" is defined here since it needs access to the dictionary "areas", defined in "run()" in "runner.py", which is unaccessible in any other part of this file
        def stars_booked(park_area: str, time_slot: int) -> list:
            area = get_park_area(park_area, areas)
            return[get_review_stars(v) for v in area.booked(time_slot)]
        return WeightedBufferManager(
            stars_booked=stars_booked, max_buffer=MAX_BUFFER_SPOTS, risk_weight=BUFFER_RISK_WEIGHT
        )
    raise ValueError(
        f"Unknown value in constants.BUFFER_STRATEGY: {strategy!r}"
        ' (Acceptable values: "legacy", "incremental", "weighted")'
    )