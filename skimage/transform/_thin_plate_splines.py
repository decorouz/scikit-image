import numpy as np
import scipy as sp


class TpsTransform:
    def __init__(self):
        self._estimated = False
        self.parameters = None
        self.src = None
        self.dst = None

    def __call__(self, coords):
        """Estimate the transformation from a set of corresponding points.

        Parameters
        ----------
        coords : (N, 2) array_like
            x, y coordinates to transform

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
        >>> coords = np.meshgrid(np.arange(5), np.arange(5))
        >>> coords = np.vstack([coords[0].ravel(), coords[1].ravel()]).T

        >>> tps = ski.transform.TpsTransform()
        >>> tps.estimate(src, dst)
        True

        Apply the transformation

        >>> trans_coord = tps(coords)
        >>> xx_trans = trans_coord[:, 0]
        >>> yy_trans = trans_coord[:, 1]
        >>> coords[1]
        array([[0, 0, 0, 0, 0],
               [1, 1, 1, 1, 1],
               [2, 2, 2, 2, 2],
               [3, 3, 3, 3, 3],
               [4, 4, 4, 4, 4]])
        >>> expected_yy = np.array([[0, 1, 2, 3, 4],
        ...                         [0, 1, 2, 3, 4],
        ...                         [0, 1, 2, 3, 4],
        ...                         [0, 1, 2, 3, 4],
        ...                         [0, 1, 2, 3, 4]])
        >>> np.allclose(yy_trans, expected_yy)
        True
        """
        if self.parameters is None:
            raise ValueError(f"{self.parameters}. Compute the `estimate`")
        coeffs = self.parameters
        coords = np.array(coords)

        if not coords.ndim == 2 or coords.shape[1] != 2:
            raise ValueError("Input 'coords' must have shape (N,2)")


        x_warp = self._spline_function(coords[:, 0], coords[:, 1], coeffs[:, 0])
        y_warp = self._spline_function(coords[:, 0], coords[:, 1], coeffs[:, 1])
        return np.vstack([x_warp, y_warp]).T

    @property
    def inverse(self):
        raise NotImplementedError("This is yet to be implemented.")

    def estimate(self, src, dst):
        """Estimate how close is the deformed source to the target.

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

        src = _ensure_2d(src)
        dst = _ensure_2d(dst)

        if src.shape != dst.shape:
            raise ValueError("src and dst shape must be identical")

        # if src.shape[-1] != 2 and dst.shape[-1] != 2:
        #     raise ValueError("src and dst must have shape (N,2)")

        self.src = src
        self.dst = dst
        n, d = src.shape

        K = self._radial_distance(src)
        P = np.hstack([np.ones((n, 1)), src])
        L = np.zeros((n+3, n+3), dtype=np.float32)
        L[:n, :n] = K
        L[:n, -3:] = P
        L[-3:, :n] = P.T
        V = np.concatenate([dst, np.zeros((d + 1, d))])
        self.parameters = np.dot(np.linalg.inv(L), V)
        self._estimated = True
        return self._estimated

    def _spline_function(self, x, y, coeffs):
        """Solve the spline function in the X and Y directions"""
        w = coeffs[:-3]
        a1, ax, ay = coeffs[-3:]
        summation = np.zeros(x.shape)
        for wi, Pi in zip(w, self.src):
            r = np.sqrt((Pi[0] - x) ** 2 + (Pi[1] - y) ** 2)
            summation += wi * _U(r)
        return a1 + ax * x + ay * y + summation

    def _radial_distance(self, points):
        """Compute the pairwise radial distances of the given points to the control points.

        Parameters
        ----------
        points : ndarray
            N points in the source space
        Returns
        -------
        ndarray :
            The radial distance for each `N` point to a control point.
        """
        dist = sp.spatial.distance.cdist(self.src, points)
        return _U(dist)


def _U(r):
    """Compute basis kernel function for thine-plate splines.

    Parameters
    ----------
    r : ndarray
        Input array representing the norm distance between interlandmark
        distances for the source form and based on the (x,y) coordinates
        for each of these points.
    Returns
    -------
    ndarray
        Calculated kernel function U.
    """
    _small = 1e-8  # Small value to avoid divide-by-zero
    return np.where(r == 0.0, 0.0, (r**2) * np.log((r**2) + _small))


def _ensure_2d(arr):
    """Ensure that `array` is a 2d array.

    In case given 1d array, expand the last dimension.
    """
    array = np.asarray(arr)

    if array.ndim not in (1, 2):
        raise ValueError("Array must be be 2D.")
    # Expand last dim in order to interpret this as (n, 1) points
    if array.ndim == 1:
        array = array[:, None]
    if array.size == 0:
        raise ValueError("Array of points can not be empty.")
    if len(array) < 3:
        raise ValueError("Array points less than 3 is undefined.")
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
    image : ndarray
        Input image.
    src : (N, 2)
        Control point at source coordinates.
    dst : (N, 2)
        Control point at target coordinates.
    output_region : tuple of integers, optional
        The region ``(xmin, ymin, xmax, ymax)`` of the output
        image that should be produced. (Note: The region is inclusive, i.e.
        xmin <= x <= xmax)
    interpolation_order : int, optional
        If value is 1, then use linear interpolation else use
        nearest-neighbor interpolation.
    grid_scaling : int, optional
        If grid_scaling is greater than 1, say x, then the transform is
        defined on a grid x times smaller than the output image region.
        Then the transform is bilinearly interpolated to the larger region.
        This is fairly accurate for values up to 10 or so.

    Returns
    -------
    warped : array_like
        The warped input image.

    References
    ----------
    .. [1] Bookstein, Fred L. "Principal warps: Thin-plate splines and the
           decomposition of deformations," IEEE Transactions on pattern analysis
           and machine intelligence 11.6 (1989): 567–585.

    Examples
    --------
    Produce a warped image rotated by 90 degrees counter-clockwise.

    >>> import skimage as ski
    >>> astronaut = ski.data.astronaut()
    >>> image = ski.color.rgb2gray(astronaut)
    >>> src = np.array([[0, 0], [0, 512], [512, 512],[512, 0]])
    >>> dst = np.array([[512, 0], [0, 0], [0, 512],[512, 512]])
    >>> output_region = (0, 0, image.shape[0], image.shape[1])
    >>> tform = ski.transform.TpsTransform()
    >>> tform.estimate(src, dst)
    True
    >>> warped_image = ski.transform.tps_warp(
    ...     image, src, dst, output_region=output_region
    ... )

    """
    image = np.asarray(image)

    if image.shape[0] == 0 or image.shape[1] == 0:
        raise ValueError(
            f"Cannot warp image with invalid shape: {image.shape}"
        )

    if image.ndim not in (2, 3):
        raise ValueError("Only 2D and 3D images are supported")

    output_region = output_region or (0, 0, image.shape[0], image.shape[1])

    x_min, y_min, x_max, y_max = output_region
    if grid_scaling is None:
        grid_scaling = 1
    x_steps = (x_max - x_min) // grid_scaling
    y_steps = (y_max - y_min) // grid_scaling
    xx, yy = np.mgrid[x_min : x_max : x_steps * 1j, y_min : y_max : y_steps * 1j]
    coords = np.vstack([xx.ravel(), yy.ravel()]).T

    tform = TpsTransform()
    tform.estimate(dst, src)
    transform = tform(coords)

    transform = transform.reshape((x_steps, y_steps, 2))
    transform = [transform[..., 0], transform[..., 1]]

    if grid_scaling != 1:
        # linearly interpolate the zoomed transform grid
        new_x, new_y = np.mgrid[x_min:x_max, y_min:y_max]
        # new_x, new_y = np.mgrid[x_min:x_max+1, y_min:y_max+1]
        x_indices = (x_steps - 1) * (new_x - x_min) / float(x_max - x_min)
        y_indices = (y_steps - 1) * (new_y - y_min) / float(y_max - y_min)

        x_indices = np.clip(x_indices, 0, x_steps - 1)
        y_indices = np.clip(y_indices, 0, y_steps - 1)

        transform_x = sp.ndimage.map_coordinates(
            transform[0], [x_indices, y_indices]
        )
        transform_y = sp.ndimage.map_coordinates(
            transform[1], [x_indices, y_indices]
        )
        transform = [transform_x, transform_y]
    if image.ndim == 2:
        warped_image = sp.ndimage.map_coordinates(
            image, transform, order=interpolation_order
        )
    else:  # RGB image
        channels = image.shape[-1]
        warped_channels = [
            sp.ndimage.map_coordinates(
                image[..., channel], transform, order=interpolation_order
            )[..., None]
            for channel in range(channels)
        ]
        warped_image = np.concatenate(warped_channels, axis=-1)

    return warped_image
