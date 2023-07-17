import numpy as np
import scipy as sp


class TPSTransform:
    """Thin plate spline transformation."""
    def __init__(self):
        self._estimated =  False
        self.parameters = np.array([], dtype=np.float32)
        self.control_points = np.array([], dtype=np.float32)


    def __call__(self, points):
        """Map the source points to the destination surface.

        Parameters
        ----------
        new_coords: array_like
            Array of source points to be transformed
        Returns
        -------
            ndarray: Mapped point of the distination point
        """
        X_src = _ensure_2d(points)

        if X_src.shape[1] != self.control_points.shape[1]:
            raise ValueError("Array must be identical")

        dist = self._radial_distance(X_src)
        transforms = np.hstack([dist, np.ones((X_src.shape[0], 1)), X_src])
        return transforms @ self.parameters

    @property
    def inverse(self):
        raise NotImplementedError("This is yet to be implemented.")

    def estimate(self, src, dst):
        """Estimate the transformation from a set of corresponding points.

        Number of source and destination points must match.

        Parameters
        ----------
        src : (N, 2) array_like
            Control point at source coordinates
        dst : (N, 2) array_like
            Control point at destination coordinates

        Returns
        -------
        success: bool
            True, if all pieces of the model are successfully estimated.
        """

        src = np.asarray(src)
        dst = np.asarray(dst)

        if src.shape != dst.shape:
            raise ValueError("src and dst shape must be identical")

        if src.shape[-1] != 2 and dst.shape[-1] != 2:
            raise ValueError("src and dst must have shape (N,2)")

        self.control_points = src
        n_pts , dim = src.shape

        K = self._radial_distance(src)
        P = np.hstack([np.ones((n_pts, 1)), src])
        O = np.zeros((3, 3))
        L = np.asarray(np.bmat([[K, P],[P.T, O]]))
        Y = np.concatenate([dst, np.zeros((dim + 1, dim))])
        self.parameters = np.dot(np.linalg.pinv(L), Y)

        self._estimated = True
        return self


    def _transform_points(self, x, y, coeffs):
        w = coeffs[:-3]
        a1, ax, ay, = coeffs[-3:]
        summation = np.zeros(x.shape)
        for wi, Pi in zip(w, self.control_points):
            r = np.sqrt((Pi[0] - x)**2 + (Pi[1] - y)**2)
            summation += wi * _U(r)
        return a1 + ax*x + ay*y + summation

    def transform(self, x, y):
        """Estimate the transformation from a set of corresponding points.

        Number of source and destination points must match.

        Parameters
        ----------
        x : array_like
            The x-coordinates of points to transform.
        y : array_like
            The y-coordinates of points to transform.

        Returns
        -------
        transformed_pts: lists
            A list of tranformed coordinates.

        Examples
        --------
        >>> import skimage as ski

        Define source and destination points and generate meshgrid for transformation:

        >>> src = np.array([[0, 0], [0, 5], [5, 5],[5, 0]])
        >>> dst = np.roll(src, 1, axis=0)
        >>> xx, yy = np.meshgrid(np.arange(5), np.arange(5))

        >>> tps = ski.transform.TPSTransform()
        >>> tps.estimate(src, dst)
        >>> xx
        array([[0, 1, 2, 3, 4],
               [0, 1, 2, 3, 4],
               [0, 1, 2, 3, 4],
               [0, 1, 2, 3, 4],
               [0, 1, 2, 3, 4]])

        Apply the transformation

        >>> xx_trans, yy_trans = tps.transform(xx, yy)
        >>> xx_trans
        array([[5., 5., 5., 5., 5.],
               [4., 4., 4., 4., 4.],
               [3., 3., 3., 3., 3.],
               [2., 2., 2., 2., 2.],
               [1., 1., 1., 1., 1.]])
        """
        coeffs =  self.parameters
        transformed_x = self._transform_points(x, y, coeffs[:, 0])
        transformed_y = self._transform_points(x, y, coeffs[:, 1])
        return [transformed_x, transformed_y]


    def _radial_distance(self, points):
        """Compute the pairwise radial distances of the given points to the control points.

        Parameters
        ----------
        points : ndarray
            N points in the source space
        Returns
        -------
        ndarray:
            The radial distance for each `N` point to a control point.
        """
        dist = sp.spatial.distance.cdist(points, self.control_points)
        _small = 1e-8  # Small value to avoid divide-by-zero
        return np.where(dist == 0.0, 0.0, (dist**2) * np.log((dist) + _small))

def _U(r):
    """Compute basis kernel function for thine-plate splines.

    Parameters
    ----------
    r: ndarray
        Input array representing the norm distance between points.
        The norm is the Euclidean distance.
    Returns
    -------
    ndarray
        Calculated kernel function U.
    """
    _small = 1e-8  # Small value to avoid divide-by-zero
    return np.where(r == 0.0, 0.0, (r**2) * np.log((r) + _small))

def _ensure_2d(array):
    """Ensure that `array` is a 2d array.

        In case given 1d array, expand the last dimension.
    """
    if array.ndim not in (1, 2):
        raise ValueError("Array can not be more than 2D")
    # Expand last dim in order to interpret this as (n, 1) points
    if array.ndim == 1:
        array = array[:, None]

    return array

def tps_warp(
    image,
    src,
    dst,
    output_region=None,
    interpolation_order=1,
    grid_scaling=None
):
    """Return an array of warped images.

    Define a thin-plate-spline warping transform that warps from the
    src to the dst, and then warp the given images by
    that transform.

    Parameters
    ----------
    image: ndarray
        Input image.
    src: (N, 2) array_like
        Source image coordinates.
    dst: (N, 2) array_like
        Destination image coordinates.
    output_region: tuple of integers, optional
        The region ``(xmin, ymin, xmax, ymax)`` of the output
        image that should be produced. (Note: The region is inclusive, i.e.
        xmin <= x <= xmax)
    interpolation_order: int, optional
        If value is 1, then use linear interpolation else use
        nearest-neighbor interpolation.
    grid_scaling: int, optional
        If grid_scaling is greater than 1, say x, then the transform is
        defined on a grid x times smaller than the output image region.
        Then the transform is bilinearly interpolated to the larger region.
        This is fairly accurate for values up to 10 or so.

    Returns
    -------
    warped: array_like
        Array of warped images.

    Examples
    --------
    Produce a warped image rotated by 90 degrees counter-clockwise:

    >>> import skimage as ski
    >>> astronaut = ski.data.astronaut()
    >>> image = ski.color.rgb2gray(astronaut)
    >>> src = np.array([[0, 0], [0, 500], [500, 500],[500, 0]])
    >>> dst = np.array([[500, 0], [0, 0], [0, 500],[500, 500]])
    >>> output_region = (0, 0, image.shape[0], image.shape[1])
    >>> warped_image = ski.transform.tps_warp(
    ...     image, src, dst, output_region=output_region
    ... )

    References
    ----------
    .. [1] Bookstein, Fred L. "Principal warps: Thin-plate splines and the
    decomposition of deformations." IEEE Transactions on pattern analysis and
    machine intelligence 11.6 (1989): 567–585.

    """
    image = np.asarray(image)

    if image.size == 0:
        raise ValueError("Cannot warp empty image with dimensions", image.shape)
    if image.ndim != 2:
        raise ValueError("Only 2-D images (grayscale or color) are supported")
    if output_region is None:
        output_region = (0, 0) + image.shape

    x_min, y_min, x_max, y_max = output_region
    if grid_scaling is None:
        grid_scaling = 1
    x_steps = (x_max - x_min) // grid_scaling
    y_steps = (y_max - y_min) // grid_scaling
    x, y = np.mgrid[x_min:x_max:x_steps*1j, y_min:y_max:y_steps*1j]

    # make the reverse transform warping from the dst to the src,
    # because we do image interpolation in this reverse fashion
    tps = TPSTransform()
    tps.estimate(dst, src)
    transform = tps.transform(x, y)


    if grid_scaling != 1:
        # linearly interpolate the zoomed transform grid
        new_x, new_y = np.mgrid[x_min:x_max, y_min:y_max]
        # new_x, new_y = np.mgrid[x_min:x_max+1, y_min:y_max+1]
        x_indices = ((x_steps - 1) * (new_x - x_min) / float(x_max - x_min))
        y_indices = ((y_steps - 1) * (new_y - y_min) / float(y_max - y_min))

        x_indices = np.clip(x_indices, 0, x_steps - 1)
        y_indices = np.clip(y_indices, 0, y_steps - 1)

        transform_x = sp.ndimage.map_coordinates(transform[0], [x_indices, y_indices])
        transform_y = sp.ndimage.map_coordinates(transform[1], [x_indices, y_indices])
        transform = [transform_x, transform_y]

    return sp.ndimage.map_coordinates(image, transform, order=interpolation_order)
