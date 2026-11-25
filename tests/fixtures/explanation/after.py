def calculateBestDistance(client, origin, destination, *, compare_modes=False):
    modes = ("driving", "walking", "bicycling") if compare_modes else ("driving",)
    distances = [client.distance_matrix(origin, destination, mode=mode) for mode in modes]
    return min(distances)
