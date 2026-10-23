from constants import STEPS_PER_CALENDAR_SLOT, PARK_AREA_NAMES, SLOTS_PER_ROW


def is_out_of_town(park_area: str) -> bool:
    """Returns true if the park area is an out of town one ("ParkAreaOutOfTown")"""
    return PARK_AREA_NAMES[2] in park_area

def step_to_calendar_slot(simulation_step: float) -> int:
    """Returns the time slot associated to the given simulation step"""
    return int(simulation_step) // STEPS_PER_CALENDAR_SLOT



class ParkArea:
    """Represents a single park area in the simulation"""
    def __init__(self, name: str, capacity: int = SLOTS_PER_ROW):
        self.name = name
        self.capacity = capacity

        self.is_out_of_town = is_out_of_town(name)

        # Numbre of active reservations of the area
        self.reservations = 0

        self.calendar = {}

    def is_fully_booked(self, buffer_spots: int) -> bool:
        """Returns True if the current reservations in the area exceed the maximum reservable spots"""
        return self.reservations > self.capacity - buffer_spots

    def has_free_slot(self, buffer_spots: int) -> bool:
        """Returns True if there are vacant reservable spots in the area"""
        return self.reservations < self.capacity - buffer_spots

    def unreserved_spots(self, first_slot: int, last_slot: int) -> int:
        """Free (unreserved) spots, needed to check if a reservation was refused beacuse the buffer takes up empty spaces"""
        spots = []
        for i in range(first_slot, last_slot):
            spots.append(len(self.calendar.get(i, ())))
        return self.capacity - max(spots)

    def can_book(self, first_slot: int, last_slot: int, buffer_of_slot) -> bool:
        """Checks if a spot can be booked for the given time windows. If even a single time window is full, the spot is not reservable"""
        for i in range(first_slot, last_slot):
            bookings_in_slot = len(self.calendar.get(i, ()))
            if bookings_in_slot >= self.capacity - buffer_of_slot(i):
                return False
        return True
    
    def book(self, id_vehicle: str, first_slot: int, last_slot: int) -> None:
        """Reserves a spot for the specified vehicle in the requested time windows"""
        for i in range(first_slot, last_slot):
            self.calendar.setdefault(i, set()).add(id_vehicle)
    
    def cancel(self, id_vehicle: str, first_slot: int, last_slot: int) -> None:
        """Removes the booking of the specified vehicle in all of its time windows"""
        for i in range(first_slot, last_slot):
            bookings_in_slot = self.calendar[i]
            bookings_in_slot.remove(id_vehicle)
            if not bookings_in_slot:
                del self.calendar[i]

    def booked(self, slot: int) -> frozenset:
        """Returns the id of the vehicles currently booked in the specified time window"""
        return frozenset(self.calendar.get(slot, ()))

def get_park_area(name: str, areas: dict) -> ParkArea:
    """Returns the park area specified in 'name', eventually creates it inside 'areas'"""
    area = areas.get(name)
    if area is None:
        area = ParkArea(name)
        areas[name] = area
    return area