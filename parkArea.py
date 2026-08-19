from constants import PARK_AREA_NAMES, SLOTS_PER_ROW


def is_out_of_town(park_area: str) -> bool:
    """Returns true if the park area is an out of town one ("ParkAreaOutOfTown")"""
    return PARK_AREA_NAMES[2] in park_area


class ParkArea:
    """Represents a single park area in the simulation"""
    def __init__(self, name: str, capacity: int = SLOTS_PER_ROW):
        self.name = name
        self.capacity = capacity

        self.is_out_of_town = is_out_of_town(name)

        # Numbre of active reservations of the area
        self.reservations = 0

    def is_fully_booked(self, buffer_spots: int) -> bool:
        """Returns True if the current reservations in the area exceed the maximum reservable spots"""
        return self.reservations > self.capacity - buffer_spots

    def has_free_slot(self, buffer_spots: int) -> bool:
        """Returns True if there are vacant reservable spots in the area"""
        return self.reservations < self.capacity - buffer_spots
    

def get_park_area(name: str, areas: dict) -> ParkArea:
    """Returns the park area specified in 'name', eventually creates it inside 'areas'"""
    area = areas.get(name)
    if area is None:
        area = ParkArea(name)
        areas[name] = area
    return area