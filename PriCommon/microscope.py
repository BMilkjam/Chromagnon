

import numpy as N

def resolution(NA=0.9, wave=515):
    return 0.61 * wave / NA

def angleFromNA(NA=0.9, n=1.0):
    """
    return angle in degrees
    """
    # NA = n sin(theta)
    # sin(theta) = NA / n
    return N.degrees(N.arcsin(NA / float(n)))


def snellsLow(n1=1.0, theta1=64.158, n2=1.515):
    """
    n1 > n2
    return angle in degrees
    """
    # n1 sin(theta1) = n2 sin(theta2)
    # sin(theta2) = n1 sin(theta1) / n2
    return N.degrees(N.arcsin((n1 * N.sin(theta1)) / float(n2)))


def diameter4imaging(z=80, n=1.33, NA=1.2):
    """
    return diameter of the circle affected by the sample
    """
    # NA = n sin(theta)
    # sin(theta) = NA / n
    theta = N.arcsin(NA / float(n))
    # tan(theta) = r / z
    r = z * N.tan(theta)
    # diamter
    return 2 * r

def helz_at_back_focal(size=1.1, z=80, n=1.33, NA=1.2, pixelSize=0.088, npix=512):
    """
    size: target size in um
    z: imaging depth in um
    return helz in the back focal plane
    """
    field = float(pixelSize) * npix
    helz_cam = field / size
    d = diameter4imaging(z, n, NA)
    factor = d / field
    return helz_cam * factor

def laserM2(m2=1.05, wave=488, diam_mm=1, distance_mm=1000):
    """
    calculates the resulting beam diameter from laser
    
    return (divergence angle in degrees, resulting beam diameter)
    """
    wave /= 10.**6 # -> mm
    
    theta = 4 * m2 * wave / (N.pi * diam_mm)

    div = distance_mm * N.tan(theta) * 2 + diam_mm

    return N.degrees(theta), div

#------------ color LUT -----------------#

COLOR_TABLE=[(1,0,1),   (0,0,1), (0,1,1), (0,1,0), (1,1,0),  (1,0,0), (1,1,1), (0,0,0)]
COLOR_NAME =['purple', 'blue',  'cyan',  'green', 'yellow', 'red', 'white', 'black']
WAVE_CUTOFF=[400,       450,     500,     530,     560,      660,   800,     1100]

def LUT(wave):
    """
    return colorTuple (R,G,B)
    """
    col = None
    for i, WAVE in enumerate(WAVE_CUTOFF):
        if wave < WAVE:
            col = COLOR_TABLE[i]
            break
    if not col:
        col = COLOR_TABLE[i+1]
    return col


def LUTname(colorTuple):
    """
    return colorname
    """
    if COLOR_TABLE.count(colorTuple):
        idx = COLOR_TABLE.index(colorTuple)
        return COLOR_NAME[idx]
    else:
        raise ValueError, 'colorTuple %s not found in COLOR_NAME list' % colorTuple
        
