import numpy as np
import scipy as sp


def warp_images(
    from_points,
    to_points,
    images,
    output_region,
    interpolation_order=1,
    approximate_grid=2
):
    """Return an array of warped images.

    Define a thin-plate-spline warping transform that warps from the
    from_points to the to_points, and then warp the given images by
    that transform.

    Parameters
    ----------
    from_points: (N, 2) array_like
        Source image coordinates.
    to_points: (N, 2) array_like
        Target image coordinates.
    images: ndarray
        Array of nD images to be warped with the given warp transform.
    output_region: (1, 4) array
        The (xmin, ymin, xmax, ymax) region of the output
        image that should be produced. (Note: The region is inclusive, i.e.
        xmin <= x <= xmax)
    interpolation_order: int, optional
        If value is 1, then use linear interpolation else use
        nearest-neighbor interpolation.
    approximate_grid: int, optional
        If approximate_grid is greater than 1, say x, then the transform is
        defined on a grid x times smaller than the output image region.
        Then the transform is bilinearly interpolated to the larger region.
        This is fairly accurate for values up to 10 or so.

    Returns
    -------
    warped: array_like
        Array of warped images.

    References
    ----------
    .. [1] Bookstein, Fred L. "Principal warps: Thin-plate splines and the
    decomposition of deformations." IEEE Transactions on pattern analysis and
    machine intelligence 11.6 (1989): 567–585.

    """
    transform = _make_inverse_warp(from_points, to_points,
                                   output_region, approximate_grid)
    return [sp.ndimage.map_coordinates(np.asarray(image), transform, order=interpolation_order) for image in images]


def _make_inverse_warp(
        from_points, to_points, output_region,
        approximate_grid):
    x_min, y_min, x_max, y_max = output_region
    if approximate_grid is None:
        approximate_grid = 1
    x_steps = (x_max - x_min) // approximate_grid
    y_steps = (y_max - y_min) // approximate_grid
    x, y = np.mgrid[x_min:x_max:x_steps*1j, y_min:y_max:y_steps*1j]

    # make the reverse transform warping from the to_points to the from_points,
    # because we do image interpolation in this reverse fashion
    transform = _make_warp(to_points, from_points, x, y)

    if approximate_grid != 1:
        # linearly interpolate the zoomed transform grid
        new_x, new_y = np.mgrid[x_min:x_max+1, y_min:y_max+1]
        x_fracs, x_indices = np.modf(
            (x_steps-1)*(new_x-x_min)/float(x_max-x_min))
        y_fracs, y_indices = np.modf(
            (y_steps-1)*(new_y-y_min)/float(y_max-y_min))
        x_indices = x_indices.astype(int)
        y_indices = y_indices.astype(int)
        x1 = 1 - x_fracs
        y1 = 1 - y_fracs
        ix1 = (x_indices+1).clip(0, x_steps-1)
        iy1 = (y_indices+1).clip(0, y_steps-1)
        t00 = transform[0][(x_indices, y_indices)]
        t01 = transform[0][(x_indices, iy1)]
        t10 = transform[0][(ix1, y_indices)]
        t11 = transform[0][(ix1, iy1)]
        transform_x = (t00*x1*y1 + t01*x1*y_fracs
                       + t10*x_fracs*y1 + t11*x_fracs*y_fracs)
        t00 = transform[1][(x_indices, y_indices)]
        t01 = transform[1][(x_indices, iy1)]
        t10 = transform[1][(ix1, y_indices)]
        t11 = transform[1][(ix1, iy1)]
        transform_y = (t00*x1*y1 + t01*x1*y_fracs
                       + t10*x_fracs*y1 + t11*x_fracs*y_fracs)
        transform = [transform_x, transform_y]
    return transform


def _U(x):
    """Compute basis kernel function for thine-plate splines.

    Parameters
    ----------
    x: ndarray
        Input array representing the norm distance between points.
        The norm is the Euclidean distance.
    Returns
    -------
    ndarray
        Calculated U values.
    """
    _small = 1e-8  # Small value to avoid divide-by-zero
    return np.where(x == 0.0, 0.0, (x**2) * np.log((x**2) + _small))

def _make_L_matrix(points):
    """Define the L matrix based on the given points.

    A (N+P+1, N+P+1)-shaped L matrix that gets inverted when calculating
    the thin-plate spline from `points`.

    Parameters
    ----------
    points: (N, 2) shaped array_like
        A (N, D) array of N landmarks in D=2 dimensions.

    Returns
    -------
    L : ndarray
        A (N+D+1, N+D+1) shaped array of the form [[K | P][P.T | 0]].
    """
    if points.ndim != 2:
        raise ValueError("The input `points` must be a 2-D tensor")
    n_pts = points.shape[0]
    P = np.hstack([np.ones((n_pts, 1)), points])
    K = _U(sp.spatial.distance.cdist(points, points, metric='euclidean'))
    O = np.zeros((3, 3))
    L = np.asarray(np.bmat([[K, P], [P.transpose(), O]]))
    return L

def _coeffs(from_points, to_points):
    """Find the thin-plate spline coefficients.

    Parameters
    ----------
    from_points : (N, 2) array_like
        An array of N points representing the source landmark.

    to_points : (N,2) array_like
        An array of N points representing the target landmark.
        `to_points` must have the same shape as `from_points`.

    Returns
    -------
    coeffs : ndarray
        Array of shape (N+3, 2) containing the calculated coefficients.

    """
    n_coords = from_points.shape[1]
    Y = np.row_stack((to_points, np.zeros((n_coords+1, n_coords))))
    L = _make_L_matrix(from_points)
    coeffs = np.dot(np.linalg.pinv(L), Y)
    return coeffs


def _calculate_f(coeffs, points, x, y):
    w = coeffs[:-3]
    a1, ax, ay = coeffs[-3:]
    # The following uses too much RAM:
    # distances = _U(np.sqrt((points[:,0]-x[...,np.newaxis])**2
    # + (points[:,1]-y[...,np.newaxis])**2))
    # summation = (w * distances).sum(axis=-1)
    summation = np.zeros(x.shape)
    for wi, Pi in zip(w, points):
        summation += wi * _U(np.sqrt((x-Pi[0])**2 + (y-Pi[1])**2))
    return a1 + ax*x + ay*y + summation


def _make_warp(from_points, to_points, x_vals, y_vals):
    from_points = np.asarray(from_points)
    to_points = np.asarray(to_points)
    err = np.seterr(divide='ignore')
    L = _make_L_matrix(from_points)
    V = np.resize(to_points, (len(to_points)+3, 2))
    V[-3:, :] = 0
    coeffs = np.dot(np.linalg.pinv(L), V)
    x_warp = _calculate_f(coeffs[:, 0], from_points, x_vals, y_vals)
    y_warp = _calculate_f(coeffs[:, 1], from_points, x_vals, y_vals)
    np.seterr(**err)
    return [x_warp, y_warp]
