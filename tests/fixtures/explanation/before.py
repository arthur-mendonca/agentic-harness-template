def calculateBestDistance(client, origin, destination, *, compare_modes=False):
    return client.distance_matrix(origin, destination, mode="driving")
