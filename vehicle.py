class Vehicle:
    """Represents a single vehicle in the simulation"""

    def __init__(self, id_vehicle: str, xml_pos: int):
        self.id = id_vehicle
        # Index of the <trip> tag relative to the vehicle in the XML routes file
        self.xml_pos = xml_pos

        # Index of the current stop of the vehicle in its stop sequence in the XML routes file
        self.stop_pos = 0

        # Name of the park area where the vehicle is currently stopped or where it's currently headed. Is None until observed for the first time 
        self.last_park = None

        # Represents the simulation step in which the vehicle should leave his currently reserved spot
        self.park_duration = None

        self.has_reservation = False

        # Checks if the vehicle paid for its current stop
        self.paid = False

        # Used only when deviating a vehicle to another area when a NO PARK situation happens; tells runner.py not to increase 'cont_no_park' while the vehicle is moving towards a park area out of town
        self.is_waiting = False

        # Checks if the vahicle changed route at least once during the entire simulation
        self.changed_route = False


    # No need for methods


def get_vehicle(id_vehicle: str, vehicles: dict, xml_pos_by_id: dict) -> Vehicle:
    """Returns the park area specified in 'id_vehicle', eventually creates it inside 'vehicles'"""
    vehicle = vehicles.get(id_vehicle)
    if vehicle is None:
        vehicle = Vehicle(id_vehicle, xml_pos_by_id[id_vehicle])
        vehicles[id_vehicle] = vehicle
    return vehicle