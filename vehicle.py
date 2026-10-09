import traci

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

        # Represents the length of the overstay for the current stop
        self.overstay = 0


    # No need for methods


def get_vehicle(id_vehicle: str, vehicles: dict, xml_pos_by_id: dict) -> Vehicle:
    """Returns the park area specified in 'id_vehicle', eventually creates it inside 'vehicles'"""
    vehicle = vehicles.get(id_vehicle)
    if vehicle is None:
        vehicle = Vehicle(id_vehicle, xml_pos_by_id[id_vehicle])
        vehicles[id_vehicle] = vehicle
    return vehicle

# Getters and setters for the various parameters, instead of calling TraCI directly

def get_review_stars(id_vehicle: str) -> int:
    return int(traci.vehicle.getParameter(id_vehicle, "reviewStars"))

def set_review_stars(id_vehicle: str, review_stars: int) -> None:
    traci.vehicle.setParameter(id_vehicle, "reviewStars", str(review_stars))

def get_warning(id_vehicle: str) -> int:
    return int(traci.vehicle.getParameter(id_vehicle, "warning"))

def set_warning(id_vehicle: str, warning: int) -> None:
    traci.vehicle.setParameter(id_vehicle, "warning", str(warning))

def get_civil(id_vehicle: str) -> int:
    return int(traci.vehicle.getParameter(id_vehicle, "civil"))

def set_civil(id_vehicle: str, civil: int) -> None:
    traci.vehicle.setParameter(id_vehicle, "civil", str(civil))

def get_wallet(id_vehicle: str) -> int:
    return int(traci.vehicle.getParameter(id_vehicle, "wallet"))

def set_wallet(id_vehicle: str, wallet: int) -> None:
    traci.vehicle.setParameter(id_vehicle, "wallet", str(wallet))

def get_good_behaviour(id_vehicle: str) -> bool:
    value = traci.vehicle.getParameter(id_vehicle, "goodBehaviour")
    if value not in ("True", "False"):
        raise ValueError(
            f'{id_vehicle}, "goodBehaviour" value is "{value}", expected "True" or "False"'
        )
    return value == "True"

def set_good_behaviour(id_vehicle: str, good_behaviour: bool) -> None:
    traci.vehicle.setParameter(id_vehicle, "goodBehaviour", str(good_behaviour))

def get_overstay_probability(id_vehicle: str) -> float:
    return float(traci.vehicle.getParameter(id_vehicle, "overstayProbability"))

def set_overstay_probability(id_vehicle: str, overstay_probability: float) -> None:
    traci.vehicle.setParameter(id_vehicle, "overstayProbability", str(overstay_probability))

def get_learning_probability(id_vehicle: str) -> float:
    return float(traci.vehicle.getParameter(id_vehicle, "learningProbability"))