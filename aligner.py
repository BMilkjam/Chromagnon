
import os
import numpy as N
from PriCommon import imgfileIO as im, mrcIO, imgGeo, imgFilters, xcorr
import alignfuncs as af, cutoutAlign
from Priithon.all import Mrc
from scipy import ndimage as nd


if __name__ == '__main__':
    from PriCommon import ppro26 as ppro
    NCPU = ppro.NCPU
    #elif os.name == 'posix':
    #from PriCommon import ppro as ppro
    #NCPU = ppro.NCPU
else:
    NCPU = 1


MAXITER = 20
MAXERROR = 0.001

# parameter structure
ZYXRM_ENTRY=['tz','ty','tx','r','mz','my','mx']
NUM_ENTRY=len(ZYXRM_ENTRY)

ZMAG_CHOICE = ['Auto', 'Always', 'Never']

# file extention
PARM_EXT='chromagnon'
IMG_SUFFIX='_ALN'#'ALN.dv'

# chromagnon file format
IDTYPE = 101

class Chromagnon(object):#im.ImageManager):

    def __init__(self, fn):
        """
        usage: 
        ## channel alignment
        ## fn: the reference image
        >>> an = Chromagnon(fn)
        >>> an.findBestChannel()
        >>> an.findAlignParamWave()
        >>> an.setRegionCutOut()
        >>> an.saveAlignedImage()
        >>> out = an.saveParm()

        ## fn2: the target image
        >>> an = Chromagnon(fn2)
        >>> an.loadParm(out2)
        >>> an.setRegionCutOut()
        >>> an.saveAlignedImage()

        ## time frame alignment
        ## fn: the reference image (time projected for 10 frames for example)
        >>> an = Chromagnon(fn)
        >>> an.findBestTimeFrame()
        >>> an.findAlignParamTime()
        >>> an.setRegionCutOut()
        >>> an.saveAlignedImage()

        """
        #im.ImageManager.__init__(self, fn)
        self.img = im.load(fn)
        
        self.copyAttr()
        self.setExtrainfo()
        self.setMaxError()
        self.setMaxIter()
        self.setReferenceTime()
        self.setReferenceWave()
        self.setReferenceZIndex()
        self.setReferenceXIndex()
        self.setImageCenter()
        self.setMultipageTiff()
        self.setphaseContrast()
        self.setEchofunc()
        self.setImgSuffix()
        self.setParmSuffix()
        
        self.alignParms = N.zeros((self.img.nt, self.img.nw, NUM_ENTRY), N.float32)
        self.alignParms[:,:,4:] = 1
        self.cropSlice = [Ellipsis, slice(None), slice(None), slice(None)]

        self.refyz = None
        self.refyx = None
        
        self.mapyx = None
        self.regions = None
        self.byteorder = '<'
        self.setCCthreshold()
        self.setMaxShift()
        self.setZmagSwitch()#setForceZmag()

    def close(self):
        if hasattr(self, 'img') and hasattr(self.img, 'close'):
            self.img.close()
        
    def copyAttr(self):
        self.nt = self.img.nt
        self.nw = self.img.nw
        self.nz = self.img.nz
        self.ny = self.img.ny
        self.nx = self.img.nx
        self.dtype = self.img.dtype
        self.hdr = self.img.hdr
        self.dirname = os.path.dirname(self.img.filename)#path)
        self.file = self.path = os.path.basename(self.img.filename)#path)

        self.t = self.img.t
        self.w = self.img.w
        self.z = self.img.z
        self.y = self.img.y
        self.x = self.img.x

        self.get3DArr = self.img.get3DArr # be carefull since after closing file, and reopen with self.img = im.load(), then this does not work anymore

    def setImgSuffix(self, suffix=IMG_SUFFIX):
        self.img_suffix = suffix

    def setParmSuffix(self, suffix=''):
        self.parm_suffix = suffix
        
    def setExtrainfo(self, extrainfo=None):
        """
        this is for images without header info
        """
        self.extrainfo = extrainfo

    def restoreDimFromExtra(self, des=False):
        """
        this is for images without header info
        """
        if self.extrainfo:
            if des:
                des.hdr.NumTimes = des.nt = self.extrainfo['nt']
                des.hdr.NumWaves = des.nw = self.extrainfo['nw']
                des.hdr.wave[:an.hdr.NumWaves] = self.extrainfo['waves']
                des.nz = des.hdr.Num[-1] // (des.hdr.NumTimes * des.hdr.NumWaves)
                des.hdr.ImgSequence = im.generalIO.IMGSEQ.index(self.extrainfo['seq'])
                des.hdr.d[:] = self.extrainfo['pixsiz']

            else:
                self.hdr.NumTimes = self.img.hdr.NumTimes = self.img.nt = self.nt = self.extrainfo['nt']
                self.hdr.NumWaves = self.img.hdr.NumWaves = self.img.nw = self.nw = self.extrainfo['nw']
                self.hdr.wave[:self.hdr.NumWaves] = self.extrainfo['waves']
                self.img.nz = self.nz = self.hdr.Num[-1] // (self.hdr.NumTimes * self.hdr.NumWaves)
                if self.t > self.nt:
                    self.t = self.nt // 2
                if self.z > self.nz:
                    self.z = self.nz // 2
                self.img.imgSequence = self.img.hdr.ImgSequence = self.hdr.ImgSequence = im.generalIO.IMGSEQ.index(self.extrainfo['seq'])
                self.img.hdr.d[:] = self.hdr.d[:] = self.extrainfo['pixsiz']

        if self.alignParms.shape != (self.img.nt, self.img.nw, NUM_ENTRY):
            self.alignParms = N.zeros((self.img.nt, self.img.nw, NUM_ENTRY), N.float32)
            self.alignParms[:,:,4:] = 1

        self.get3DArr = self.img.get3DArr
                
    def setMaxError(self, val=MAXERROR):#0.001):
        """
        if pixel size is set, then val is um
        otherwise, in pixel

        set self.maxErr, self.maxErrYX, self.maxErrZ
        """
        self.maxErr = val

        self.maxErrYX = self.maxErr / N.mean(self.img.hdr.d[:2])
        self.maxErrZ = self.maxErr / self.img.hdr.d[2]

    def setMaxIter(self, val=MAXITER):
        """
        set the maximum number of iterations

        set self.niter
        """
        self.niter = val

    def setCCthreshold(self, val=af.CTHRE):
        """
        set the threshold to check the quality of cross-correlation
        
        set self.cthre
        """
        self.cthre = val

    def setMaxShift(self, um=af.MAX_SHIFT):
        self.max_shift_pxl = um / N.mean(self.img.hdr.d[:2])
        if self.max_shift_pxl > min((self.img.nx, self.img.ny)):
            self.max_shift_pxl = min((self.img.nx, self.img.ny))

    old=""""
    def setForceZmag(self, value=False):
        if value:
            self.if_failed = 'simplex'
        else:
            self.if_failed = 'terminate'      """ 

    def setZmagSwitch(self, value='Auto'):
        self.zmagSwitch = value

    def setEchofunc(self, func=None):
        self.echofunc = func

    def echo(self, msg=''):
        if self.echofunc:
            self.echofunc(msg)
        else:
            print msg
        
    def setReferenceTime(self, t=0):
        """
        set self.reftlist
        """
        iforgot="""
        if tlist is None:
            self.reftlist = xrange(self.img.nt)
        elif len(tlist) != self.img.nt:
            raise ValueError, 'tlist must have the length of time frames'
        else:
            self.reftlist = tlist"""
        self.reftime = t

    def setReferenceWave(self, wave=0):
        """
        set self.refwave (index)
        """
        self.refwave = wave

    def setReferenceZIndex(self, zs=None):
        """
        set self.refzs
        reset everytime at every time frame
        """
        self.refzs = zs

    def setReferenceXIndex(self, xs=None):
        """
        set self.refxs
        reset everytime at every time frame
        """
        self.refxs = xs

    def setAlignParam(self, param):
        """
        set 
        """
        # expand drift results if necessary
        if (self.img.nt / float(param.shape[0])) > 1:
            param2 = N.empty((self.img.nt, self.img.nw, param.shape[-1]), param.dtype)
            for w in range(self.img.nw):
                for d in range(param.shape[-1]):
                    if param.shape[0] == 1:
                        param2[:,w,d] = param[0,w,d]
                    else:
                        param2[:,w,d] = nd.zoom(param[:,w,d], self.img.nt / float(param.shape[0]))
            param = param2
        
        self.alignParms[:] = param

        self.fixAlignParmWithCurrRefWave()


    def fixAlignParmWithCurrRefWave(self):
        """
        re-organize align parameters and mapping parameters according to the current reference wave
        """
        param = N.empty((self.img.nt, self.img.nw, self.alignParms.shape[-1]), self.alignParms.dtype)

        for t in range(self.img.nt):
            for w in range(self.img.nw):
                param[t,w] = self.getShift(w,t)
        self.alignParms[:] = param

        if self.mapyx is not None:
            mapyx = N.empty_like(self.mapyx)
            for t, tmp in enumerate(self.mapyx):
                for w, wmp in enumerate(tmp):
                    mapyx[t,w] = wmp - self.mapyx[t,self.refwave]
            self.mapyx = mapyx

    def setImageCenter(self, yx=None):
        """
        use this function to chage image center

        set self.dyx
        """
        if yx is None:
            self.dyx = (0,0)
        else:
            center = N.array((self.img.ny,self.img.nx), N.float32) // 2
        
            self.dyx = yx - center


    def setphaseContrast(self, phaseContrast=True):
        self.phaseContrast = phaseContrast
        
    ### find alignment parameters of multicolor images ####
        
    def findBestChannel(self, t=0):
        """
        the reference wavelength is determined from the wavelength and intensity
        
        set self.refwave (in index)
        """
        pwrs = N.array([self.img.get3DArr(w=w, t=t).mean() for w in range(self.img.nw)])
        # if wavelengths are only 2, then use the channel with the highest signal
        if self.img.nw <= 2:
            refwave = N.argmax(pwrs)

        # take into account for the PSF distortion due to chromatic aberration
        elif self.img.nw > 2:
            # the middle channel should have the intermediate PSF shape
            waves = [mrcIO.getWaveFromHdr(self.img.hdr, w) for w in range(self.img.nw)]
            waves.sort()
            candidates = [mrcIO.getWaveIdxFromHdr(self.img.hdr, wave) for wave in waves[1:-1]]

            # find out channels with enough signal
            thr = N.mean(pwrs) / 1.25
            bol = N.where(pwrs[candidates] > thr, 1, 0)
            if N.any(bol):
                ids = N.nonzero(bol)[0]
                if len(ids) == 1:
                    idx = ids[0]
                else:
                    candidates = N.array(candidates)[ids]
                    idx = N.argmax(pwrs[candidates])

                refwave = candidates[idx]
            else:
                refwave = N.argmax(pwrs)
        self.refwave = refwave

        self.fixAlignParmWithCurrRefWave()

    
    def setRefImg(self, refyz=None, refyx=None):
        """
        set self.refyz and self.refyx
        """
        if refyz is None or refyx is None:
            if self.img.nz > 1:
                ref = self.img.get3DArr(w=self.refwave, t=self.reftime)
                if refyx is None:
                    if self.refzs is None:
                        self.refzs = af.findBestRefZs(ref)
                        print  'using slices', self.refzs

                    self.zs = N.array(self.refzs)
                    refyx = af.prep2D(ref, zs=self.refzs)

                if refyz is None:
                    if self.refxs is None:
                        self.refxs = af.findBestRefZs(ref.T)
                    self.xs = N.array(self.refxs)
                    refyz = af.prep2D(ref.T, zs=self.refxs)
                del ref
            elif refyx is None:
                refyx = self.img.getArr(w=self.refwave, t=self.reftime, z=0)

        self.refyz = refyz
        self.refyx = refyx

    def findAlignParamWave(self, t=0, doWave=True, init_t=None):
        """
        do findBestChannel() before calling this function

        init_t: time frame for the initial guess, None uses the same as t

        return nw*[tz,ty,tx,r,mz,my,mx]
        """
        if self.refyz is None or self.refyx is None:
            self.setRefImg()

        if init_t is None:
            init_t = t

        ret = self.alignParms[init_t].copy()
        
        if N.any(ret[:,:-3]):
            doXcorr = False
        else:
            doXcorr = True

        for w in range(self.img.nw):
            if (doWave and w == self.refwave) or (not doWave and w != self.refwave):
                continue

            # vertical alignment
            if self.img.nz > 1:
                img = self.img.get3DArr(w=w, t=t)
                # get initial guess if no initial guess was given
                if doXcorr:
                    self.echo('makeing an initial guess for wave %i' % w)
                    ref = self.img.get3DArr(w=self.refwave, t=t)
                    prefyx = N.max(ref, 0)
                    pimgyx = N.max(img, 0)
                    searchRad = self.max_shift_pxl * 2
                    if searchRad > min((self.img.nx, self.img.ny)):
                        searchRad = min((self.img.nx, self.img.ny))
                    yx, c = xcorr.Xcorr(prefyx, pimgyx, phaseContrast=self.phaseContrast, searchRad=searchRad)
                    ret[w,1:3] = yx
                    del ref, c
                # create 2D projection image
                self.echo('calculating shifts for wave %i' % w)
                xs = N.round_(self.refxs-ret[w,2]).astype(N.int)
                if xs.max() >= self.img.nx:
                    xsbool = (xs < self.img.nx)
                    xsinds = N.nonzero(xsbool)[0]
                    xs = xs[xsinds]

                imgyz = af.prep2D(img.T, zs=xs)

                # try quadratic cross correlation
                zdif = max(self.refzs) - min(self.refzs)
                if (self.zmagSwitch != ZMAG_CHOICE[2]) and ((zdif > 5 and self.img.nz > 30) or self.zmagSwitch == ZMAG_CHOICE[1]):#!= #'terminate':
                    initguess = N.zeros((5,), N.float32)
                    initguess[:2] = ret[w,:2][::-1]
                    initguess[2:] = ret[w,3:6]

                    if zdif > 5 and self.img.nz > 10 and self.zmagSwitch == ZMAG_CHOICE[1]:#'simplex':
                        if_failed = 'force_simplex'
                    else:
                        if_failed = 'terminate'#self.if_failed
                    
                    check = af.iteration(imgyz, self.refyz, maxErr=self.maxErrZ, niter=self.niter, phaseContrast=self.phaseContrast, initguess=initguess, echofunc=self.echofunc, max_shift_pxl=self.max_shift_pxl, if_failed=if_failed)#'force_simplex')#self.if_failed)
                    if check is not None:
                        ty2,tz,_,_,mz = check
                        ret[w,0] = tz
                        ret[w,4] = mz
                    else: # chage to normal cross correlation
                        initguess = ret[w,:2][::-1]
                        yz = af.iterationXcor(imgyz, self.refyz, maxErr=self.maxErrZ, niter=self.niter, phaseContrast=self.phaseContrast, initguess=initguess, echofunc=self.echofunc)
                        ret[w,0] = yz[1]
                # since number of section is not enough, do normal cross correlation
                else:
                    initguess = ret[w,:2][::-1]
                    yz = af.iterationXcor(imgyz, self.refyz, maxErr=self.maxErrZ, niter=self.niter, phaseContrast=self.phaseContrast, initguess=initguess, echofunc=self.echofunc)
                    ret[w,0] = yz[1]


                zs = N.round_(self.refzs-ret[w,0]).astype(N.int)
                if zs.max() >= self.img.nz:
                    zsbool = (zs < self.img.nz)
                    zsinds = N.nonzero(zsbool)[0]
                    zs = zs[zsinds]

                imgyx = af.prep2D(img, zs=zs)
                del img
            else:
                imgyx = self.img.getArr(w=w, t=t, z=0)

            initguess = N.zeros((5,), N.float32)
            initguess[:3] = ret[w,1:4] # ty,tx,r
            initguess[3:] = ret[w,5:7] # my, mx
            try:
                ty,tx,r,my,mx = af.iteration(imgyx, self.refyx, maxErr=self.maxErrYX, niter=self.niter, phaseContrast=self.phaseContrast, initguess=initguess, echofunc=self.echofunc, max_shift_pxl=self.max_shift_pxl)
            except ZeroDivisionError:
                if self.phaseContrast:
                    ty,tx,r,my,mx = af.iteration(imgyx, self.refyx, maxErr=self.maxErrYX, niter=self.niter, phaseContrast=False, initguess=initguess, echofunc=self.echofunc, max_shift_pxl=self.max_shift_pxl)
                else: # XY alignment failed
                    raise
            ret[w,1:4] = ty,tx,r
            ret[w,5:7] = my,mx

            if self.img.nz > 1:
                self.echo('time: %i, wave: %i, tx:%.3f, ty:%.3f, tz:%.3f, r:%.3f, mx:%.3f, my:%.3f, mz:%.3f' % (t,w,tx,ty,ret[w,0],r,mx,my,ret[w,4]))
            else:
                self.echo('time: %i, wave: %i, tx:%.3f, ty:%.3f, r:%.3f, mx:%.3f, my:%.3f' % (t,w,tx,ty,r,mx,my))



        self.alignParms[t] = ret


        # final 3D cross correlation
        searchRad = self.max_shift_pxl * 2
        if searchRad > min((self.img.nx, self.img.ny)):
            searchRad = min((self.img.nx, self.img.ny))

        ref = self.get3DArrayAligned(w=self.refwave, t=t)
        for w in xrange(self.img.nw):
            if (doWave and w == self.refwave) or (not doWave and w != self.refwave):
                continue

            self.echo('3D cross correlation for wave %i' % w)
            img = self.get3DArrayAligned(w=w, t=t)
            zyx, c = xcorr.Xcorr(ref, img, phaseContrast=self.phaseContrast, searchRad=searchRad)
            self.alignParms[t,w,:3] += zyx
            print 'the result of the last correlation', zyx

    ##-- non linear ----
    def findNonLinear2D(self, t=0, npxls=af.MIN_PXLS_YX, phaseContrast=True):
        """
        calculate local cross correlation of projection images

        set self.mapyx and self.regions
        """
        if self.refyz is None or self.refyx is None:
            self.setRefImg()

        # preparing the initial mapyx
        # mapyx is not inherited to avoid too much distortion
        self.mapyx = N.empty((self.img.nt, self.img.nw, 2, self.img.ny, self.img.nx), N.float32)

        # mapyx is inherited 20160727
        canceled = """ 20160830
        if self.mapyx is None:
            self.mapyx = N.empty((self.img.nt, self.img.nw, 2, self.img.ny, self.img.nx), N.float32)
        elif self.mapyx.ndim == 6:
            self.mapyx = N.mean(self.mapyx, axis=2)"""
            
        if N.all((N.array(self.mapyx.shape[-2:]) - self.img.shape[-2:]) >= 0):
            slcs = imgGeo.centerSlice(self.mapyx.shape[-2:], win=self.img.shape[-2:], center=None)
            self.mapyx = self.mapyx[[Ellipsis]+slcs]
        else:
            self.mapyx = imgFilters.paddingValue(self.mapyx, shape=self.img.shape[-2:], value=0)

        # calculation
        for w in range(self.img.nw):
            if w == self.refwave:
                self.mapyx[t,w] = 0
                continue

            self.echo('Projection local alignment -- W: %i' % w)
            if self.img.nz > 1:
                img = self.img.get3DArr(w=w, t=t)

                zs = N.round_(self.refzs-self.alignParms[t,w,0]).astype(N.int)
                if zs.max() >= self.img.nz:
                    zsbool = (zs < self.img.nz)
                    zsinds = N.nonzero(zsbool)[0]
                    zs = zs[zsinds]

                imgyx = af.prep2D(img, zs=zs)
                del img
            else:
                imgyx = N.squeeze(self.img.get3DArr(w=w, t=t))
            
            affine = self.alignParms[t,w]

            yxs, regions, arr2 = af.iterWindowNonLinear(imgyx, self.refyx, npxls, affine=affine, initGuess=self.mapyx[t,w], phaseContrast=self.phaseContrast, maxErr=self.maxErrYX, cthre=self.cthre, echofunc=self.echofunc)

            self.mapyx[t,w] = yxs
            if self.regions is None or self.regions.shape[-2:] != regions.shape:
                self.regions = N.zeros((self.img.nt, self.img.nw)+regions.shape, N.uint16)
            self.regions[t,w] = regions

            # add final 3D corss correlation
            # this is not necessary if 3D cross correlation was done in global registration
            old="""
            self.echo('The final cross correlation for wave %i' % w)
            img = self.get3DArrayRemapped(w=w, t=t)

            searchRad = self.max_shift_pxl * 2
            if searchRad > min((self.img.nx, self.img.ny)):
                searchRad = min((self.img.nx, self.img.ny))
            if 0: # only Z
                ref = self.img.get3DArr(w=self.refwave, t=t)#get3DArrayRemapped(w=self.refwave, t=t)
                prefyz = af.prep2D(ref.T, zs=self.refxs)
                pimgyz = af.prep2D(img.T, zs=self.refxs)
                yz, c = xcorr.Xcorr(prefyz, pimgyz, phaseContrast=self.phaseContrast, searchRad=searchRad)
                self.alignParms[t,w,0] += yz[1]
                print 'the result of the last correlation', yz
            else: # 3D
                ref = self.get3DArrayRemapped(w=self.refwave, t=t)
                print 'ref.max(), img.max()', ref.max(), img.max()
                zyx, c = xcorr.Xcorr(ref, img, phaseContrast=self.phaseContrast, searchRad=searchRad)
                self.alignParms[t,w,:3] += zyx
                print 'the result of the last correlation', zyx
            del img, ref, c"""
            
        return arr2

    def findNonLinear3D(self, t=0, npxls=32, phaseContrast=True):
        """
        calculate local cross correlation of 3D images section-wise

        set self.mapyx and self.regions
        """
        if self.mapyx is not None and self.mapyx.ndim == 5:
            fixGuess = True
            projmap = self.mapyx[t]
        else:
            fixGuess = False
            
        self.mapyx = N.zeros((self.img.nt, self.img.nw, self.img.nz, 2, self.img.ny, self.img.nx), N.float32)

        ref3D = self.img.get3DArr(w=self.refwave, t=t)
        refvar = ref3D.var()
        del ref3D

        for w in range(self.img.nw):
            if w == self.refwave:
                continue

            tzs = N.round_(N.arange(self.img.nz, dtype=N.float32)-self.alignParms[t,w,0]).astype(N.int)
            arr3D = self.get3DArr(w=w, t=0)
            var = (refvar + arr3D.var()) / 2.
            threshold = var * 0.1

            arr3D = af.trans3D_affineVertical(arr3D, self.alignParms[t,w])

            for z in range(self.img.nz):
                if tzs[z] > 0 and tzs[z] < self.img.nz:
                    ref = self.img.getArr(t=t,w=self.refwave,z=z)
                    arr = arr3D[z]

                    if fixGuess:
                        initGuess = projmap[w]
                    else:
                        if z:
                            initGuess = self.mapyx[t,w,z-1]
                        else:
                            initGuess = None
                    print 'Section-wise local alignment -- W: %i, Z: %i' % (w, z)
                    yxs, regions,arr2 = af.iterWindowNonLinear(arr, ref, initGuess=initGuess, affine=self.alignParms[t,w], threshold=threshold, phaseContrast=self.phaseContrast, maxErr=self.maxErrYX, cthre=self.cthre, echofunc=self.echofunc)
                    self.mapyx[t,w,z] = yxs
                    if self.regions is None or self.regions.shape[-2:] != regions.shape or self.regions.ndim == 4:
                        self.regions = N.zeros((self.img.nt, self.img.nw, self.img.nz)+regions.shape, N.uint16)
                    self.regions[t,w,z] = regions

                    #if z > 5:
                    #break
        return arr2

    def findNonLinear3D2(self, t=0, npxl=32, phaseContrast=True):
        """
        calculate local cross correlation of 3D images section-wise

        set self.mapyx and self.regions
        """
        if self.mapyx is not None and self.mapyx.ndim == 5:
            fixGuess = True
            projmap = self.mapyx[t]
        else:
            fixGuess = False
            
        self.mapyx = N.zeros((self.img.nt, self.img.nw, self.img.nz, 2, self.img.ny, self.img.nx), N.float32)

        ref3D = self.img.get3DArr(w=self.refwave, t=t)
        refvar = ref3D.var()
        del ref3D
        
        for w in range(self.img.nw):
            if w == self.refwave:
                continue

            tzs = N.round_(N.arange(self.img.nz, dtype=N.float32)-self.alignParms[t,w,0]).astype(N.int)
            arr3D = self.get3DArr(w=w, t=0)
            var = (refvar + arr3D.var()) / 2.
            threshold = var * 0.1
            
            affine = self.alignParms[t,w]
            
            arr3D = af.trans3D_affineVertical(arr3D, self.alignParms[t,w])


            if fixGuess:
                initGuess = projmap[w]
                arr_ref_guess = [(arr3D[z], self.img.getArr(w=self.refwave, t=t, z=z), initGuess) for z in range(8) if tzs[z] > 0 and tzs[z] < self.img.nz]
            else:
                initGuess = N.zeros(self.mapyx.shape[-4:])
                initGuess[1:] = self.mapyx[t,w,:-1]

                arr_ref_guess = [(arr3D[z], self.img.getArr(w=self.refwave, t=t, z=z), initGuess[z]) for z in range(range(8)) if tzs[z] > 0 and tzs[z] < self.img.nz]
            del arr3D
            
            # prepare for multiprocessing
            if NCPU == 1:
                yxs_regions = [af.findNonLinearSection(arg, npxl, affine, threshold, phaseContrast, self.maxErrYX) for arg in arr_ref_guess]
            else:
                yxs_regions = ppro.pmap(af.findNonLinearSection, arr_ref_guess, NCPU, npxl, affine, threshold, phaseContrast, self.maxErrYX)
            for z, yr in enumerate(yxs_regions):
                yxs, regions = yr
                self.mapyx[t,w,z] = yxs
                if self.regions is None or self.regions.shape[-2:] != regions.shape or self.regions.ndim == 4:
                    self.regions = N.zeros((self.img.nt, self.img.nw, self.img.nz)+regions.shape, N.uint16)
                self.regions[t,w,z] = regions

                if z > 5:
                    break
                    #return arr2

    def _findNonLinearSection(self, arr_ref_guess, affine, threshold):
        arr, ref, guess = arr_ref_guess
        return af.iterNonLinear(arr, ref, affine=affine, initGuess=guess, threshold=threshold, phaseContrast=self.phaseContrast, maxErr=self.maxErrYX)
        
        
    ### find alignment parameters of timelapse images ####
    def findBestTimeFrame(self, w=0):
        """
        set self.reftime
        """
        
        pwrs = N.array([self.img.get3DArr(w=w, t=t).mean() for t in range(self.img.nt)])

        reftime = N.argmax(pwrs)

        self.reftime = reftime

    def findAlignParamTime(self, doWave=False, doMag=False):
        """
        do findBestChannel() before calling this function

        initguess: nw*[tz,ty,tx,r,mz,my,mx]

        return nw*[tz,ty,tx,r,mz,my,mx]
        """
        niter = self.niter
        self.niter = 3
        for t in range(self.img.nt):
            if t == self.reftime:
                continue

            if t == 0:
                init_t = 0
            else:
                init_t = t - 1
                                    
            self.findAlignParamWave(t=t, doWave=doWave, init_t=init_t)
            if not doMag:
                self.alignParms[t,self.refwave,4:] = 1
                
            if not doWave and self.img.nw > 1:
                for w in range(self.img.nw):
                    self.alignParms[t,w] = self.alignParms[t,self.refwave]

        self.niter = 3


    ### save and load align parameters

    def saveParm(self, fn=None):
        """
        save a chromagnon file
        (as a Mrc file format)

        return output file name
        """
        if not fn:
            fn = os.path.extsep.join((self.img.filename + self.parm_suffix, PARM_EXT))

        hdr = mrcIO.makeHdr_like(self.hdr)
        hdr.ImgSequence = 2
        hdr.PixelType = 2

        hdr.type = IDTYPE
        hdr.n1 = self.refwave
        
        if self.mapyx is None:
            hdr.Num[0] = NUM_ENTRY
            hdr.Num[1] = 1
            hdr.Num[2] = self.img.nt * self.img.nw
            hdr.n2 = 1
            
            # squeeze shape
            parm = N.squeeze(self.alignParms.reshape((self.img.nt, self.img.nw, NUM_ENTRY)))
            parm = parm.reshape(parm.shape[:-1] + (1,1) + (parm.shape[-1],))

            Mrc.save(parm, fn, hdr=hdr, ifExists='overwrite')
        else:
            parm = self.alignParms.reshape((self.img.nt * self.img.nw, NUM_ENTRY))
            hdr.NumFloats = self.alignParms.shape[-1]
            hdr.NumIntegers = 1

            extFloats = N.zeros((self.img.nt * self.img.nw * self.img.nz * 2,NUM_ENTRY), N.float32)

            extFloats[:self.img.nt * self.img.nw] = parm

            mapyx = self.mapyx
            mapyx = mapyx.reshape(mapyx.shape[:2] + (N.prod(mapyx.shape[2:-2]),) + mapyx.shape[-2:])

            hdr.Num[-1] = N.prod(mapyx.shape[:-2])
            hdr.n2 = 2

            o = mrcIO.MrcWriter(fn, hdr, extFloats=extFloats)
            for t in range(self.img.nt):
                for w in range(self.img.nw):
                    o.write3DArr(mapyx[t,w], w=w, t=t)
            o.close()

        return fn

    def loadParm(self, fn):
        """
        load a chromagnon file
        """
        arr = Mrc.bindFile(fn)

        if arr.Mrc.hdr.type != IDTYPE:
            raise ValueError, 'This file is not a valid chromagnon file'

        # reading the header
        dratio = arr.Mrc.hdr.d / self.img.hdr.d
        dratio = dratio[::-1] # zyx
        
        pwaves = list(arr.Mrc.hdr.wave[:arr.Mrc.hdr.NumWaves])
        twaves = list(self.img.hdr.wave[:self.img.nw])
        tids = [twaves.index(wave) for wave in pwaves if wave in twaves]
        pids = [pwaves.index(wave) for wave in twaves if wave in pwaves]
        refwave = pwaves[arr.Mrc.hdr.n1]
        somewaves = [w for w, wave in enumerate(pwaves) if wave in twaves]
        if refwave in twaves:
            self.refwave = twaves.index(refwave)
        elif len(somewaves) >= 1: # the reference wavelength was not found but some found
            self.refwave = somewaves[0]
            from PriCommon import guiFuncs as G
            message = 'The original reference wavelength %i was not found in the target %s' % (refwave, self.file)
            G.openMsg(msg=message, title='WARNING')

        else:
            self.parm = N.zeros((arr.Mrc.hdr.NumTimes, self.img.nw, NUM_ENTRY), arr.dtype.type)
            from PriCommon import guiFuncs as G
            message = 'No common wavelength was found in %s and %s' % (os.path.basename(fn), self.img.file)
            G.openMsg(msg=message, title='WARNING')
            return

        # obtain affine parms
        target = N.zeros((arr.Mrc.hdr.NumTimes, self.img.nw, NUM_ENTRY), arr.dtype.type)
        target[:,:,4:] = 1

        if arr.Mrc.hdr.n2 == 1:
            parm = arr
            nentry = NUM_ENTRY
        else:
            parm = arr.Mrc.extFloats[:arr.Mrc.hdr.NumTimes * arr.Mrc.hdr.NumWaves,:arr.Mrc.hdr.NumFloats]
            nentry = arr.Mrc.hdr.NumFloats
        parm = parm.reshape((arr.Mrc.hdr.NumTimes, arr.Mrc.hdr.NumWaves, nentry))

        target[:,tids] = parm[:,pids]
        for w in [w for w, wave in enumerate(twaves) if wave not in pwaves]:
            target[:,w] = parm[:,self.refwave]
        target[:,:,:3] *= dratio

        self.setAlignParam(target)


        # obtain mapping array
        # 
        hdr = arr.Mrc.hdr
        if hdr.n2 == 2:
            # pixel size adjustment + time, wavelength
            nz = hdr.Num[-1] / (hdr.NumTimes * hdr.NumWaves * 2)
            if nz == 1:
                dratio[0] = 1
            arr = arr.reshape((hdr.NumTimes, 
                               hdr.NumWaves, 
                               nz, 
                               2, 
                               hdr.Num[1], 
                               hdr.Num[0]))

            if any(dratio[1:] != 1):
                nzyx = hdr.Num[::-1].copy()
                nzyx[0] = nz
                nzyx *= dratio
                arr2 = N.empty((self.img.nt, self.img.nw, nzyx[0], 2, nzyx[1], nzyx[2]), arr.dtype.type)

                tmin = min(self.img.nt, hdr.NumTimes)
                for t, tarr in enumerate(arr):
                    if t < tmin:
                        for wt, wp in enumerate(pids):
                            for s in xrange(2):
                                warr = tarr[wp,:,s]
                                w = tids[wt]
                                arr2[t,w,:,s] = nd.zoom(warr, dratio) * dratio[1+(s%2)]
                for w in [w for w, wave in enumerate(twaves) if wave not in pwaves]:
                    arr2[:tmin,w] = arr2[:tmin,self.refwave]

                if nz == 1:
                    arr2 = arr2[:,:,0]

                arr = arr2
                del arr2

            self.mapyx = arr

            self.fixAlignParmWithCurrRefWave()

        
    ### applying alignment parameters ####

    def getShift(self, w=0, t=0, refwave=None):
        """
        return shift at the specified wavelength and time frame
        """
        if refwave is None:
            refwave = self.refwave

        ret = self.alignParms[t,w].copy()
        ref = self.alignParms[t,refwave]

        ret[:4] -= ref[:4]
        if len(ref) >= 5:
            ret[4:] /= ref[4:len(ret)]
        return ret
        
    def setRegionCutOut(self):#makeSlice(self):
        """
        return slc, shiftZYX
        """
        ZYX = N.array((self.img.nz, self.img.ny, self.img.nx))

        shiftZYX = N.zeros((self.img.nt, self.img.nw, 6), N.float32)
        shiftZYX[:,:,1::2] = ZYX
        
        for t in range(self.img.nt):
            for w in range(self.img.nw):
                if w != self.refwave:
                    shift = self.getShift(w=w, t=t)
                    shiftZYX[t,w] = cutoutAlign.getShift(shift, ZYX)

        mm = shiftZYX[:,:,::2].max(0).max(0)
        MM = shiftZYX[:,:,1::2].min(0).min(0)

        shiftZYX = N.array((mm[0], MM[0], mm[1], MM[1], mm[2], MM[2]))

        # rearrange as a slice
        slc = [Ellipsis, 
               slice(shiftZYX[0], shiftZYX[1]),
               slice(shiftZYX[2], shiftZYX[3]),
               slice(shiftZYX[4], shiftZYX[5])]
        
        #return slc#, shiftZYX
        self.cropSlice = slc

    # def setRegionCutOut(self):
    #     """
    #     use self.alignParms
    #     set self.copSlice
    #     """
    #     #slc, shift = self.makeSlice()
    #     slc = self.makeSlice()
    #     self.cropSlice = slc

    def get3DArrayAligned(self, w=0, t=0):
        """
        use self.setRegionCutOut() prior to calling this function if the img is to be cutout
        
        dyx: shift from the center of rotation & magnification

        return interpolated array
        """
        arr = self.img.get3DArr(w=w, t=t)

        self.img.close() # to avoid the error (too many open files) on Mac with multiprocessing
        arr = af.applyShift(arr, self.alignParms[t,w])#, self.alignParms[t,w,:3])
        self.img = im.load(os.path.join(self.dirname, self.file))
        self.restoreDimFromExtra()

        arr = arr[self.cropSlice]
        
        return arr

    def get3DArrayRemapped(self, w=0, t=0):
        """
        use self.setRegionCutOut() prior to calling this function if the img is to be cutout
        
        dyx: shift from the center of rotation & magnification

        return interpolated array
        """
        if self.mapyx is None:
            raise RuntimeError, 'This method must be called after calling "findNonLinear2D"'
        
        arr = self.img.get3DArr(w=w, t=t)
        
        self.img.close() # to avoid the error (too many open files) on Mac with multiprocessing
        arr = af.remapWithAffine(arr, self.mapyx[t,w], self.alignParms[t,w])
        self.img = im.load(os.path.join(self.dirname, self.file))
        self.restoreDimFromExtra()
        
        #arr = arr[self._zIdx]
        arr = arr[self.cropSlice]#_yxSlice]
        
        return arr


    ### saving image into a file ###


    def setMultipageTiff(self, multi=True):
        """
        set self.multipagetif
        use before saving tiff files
        """
        self.multipagetif = multi

    def prepSaveFile(self, fn):
        """
        return file hander class (either ImageWriter or MrcWriter)

        use self.setRegionCutOut() prior to calling this function if the img is to be cutout
        """
        hdr = mrcIO.makeHdr_like(self.img.hdr)
        #hdr.Num[:2] = self._yxSize[::-1]
        hdr.Num[0] = self.cropSlice[-1].stop - self.cropSlice[-1].start
        hdr.Num[1] = self.cropSlice[-2].stop - self.cropSlice[-2].start
        hdr.Num[2] = self.img.nt * self.img.nw * (self.cropSlice[-3].stop - self.cropSlice[-3].start)#len(self._zIdx)
        #hdr.ntst = self._tIdx[0]
        #hdr.mst[:2] = self._yxSlice[1].start, self._yxSlice[0].start
        #hdr.mst[-1] = self._zIdx[0]
        hdr.mst[:] = [s.start for s in self.cropSlice[::-1][:-1]]

        if os.path.splitext(fn)[1][1:].lower() in im.IMGEXTS_MULTITIFF:#['tif', 'tiff']:
            des = im.MultiTiffWriter(fn, self.multipagetif)
            des.setDimFromMrcHdr(hdr)
            #des.dtype = N.float32
            des.setSecSize()
            #des.setParameters(metadata={'axes': 'ZYX'})
        else:
            extInts = None
            extFloats = None
            if hasattr(self.img.hdr, 'NumIntegers') and self.img.hdr.NumIntegers and hasattr(self.img, 'extInts'):
                extInts = self.img.extInts
            if hasattr(self.img.hdr, 'NumFloats') and self.img.hdr.NumFloats and hasattr(self.img, 'extFloats'):
                extFloats = self.img.extFloats
            
            des = mrcIO.MrcWriter(fn, hdr, extInts, extFloats, byteorder=self.byteorder)

        return des

    def min_is_zero(self):
        """
        return True if minimum of all sections is 0
        """
        if self.dtype == N.float32:
            for t in range(self.img.nt):
                for w in range(self.img.nw):
                    arr = self.img.get3DArr(w=w, t=t)
                    if arr.min() != 0:
                        return
            return True

    def saveAlignedImage(self, fn=None):
        """
        save aligned image into a file

        return output file name
        """
        base, ext = os.path.splitext(self.img.filename)
        if ext[1:].lower() in im.IMGEXTS_MULTITIFF:
            target_is_mrc = False
        else:
            target_is_mrc = True

        if not fn:
            if target_is_mrc:
                if self.img.filename.endswith('.dv'):
                    #img_suffix = os.path.splitext(IMG_SUFFIX)[0]
                    #fn = base + '_' + self.img_suffix + ext
                    fn = base + self.img_suffix + ext
                else:
                    fn = self.img.filename + self.img_suffix + '.dv'#IMG_SUFFIX))
            else:
                #fn = base + '_aln' + ext
                #fn = base + '_' + self.img_suffix + ext
                fn = base + self.img_suffix + ext

        min0 = self.min_is_zero()
                
        des = self.prepSaveFile(fn)

        for t in range(self.img.nt):
            for w in range(self.img.nw):
                
                if w == self.refwave and self.nt == 1:
                    arr = self.img.get3DArr(w=w, t=t)
                    #arr = arr[self._zIdx]
                    arr = arr[self.cropSlice]#_yxSlice]
                elif self.mapyx is None:
                    self.echo('Applying affine transformation to the target image, t: %i, w: %i' % (t, w))
                    if target_is_mrc:
                        des.close()
                    arr = self.get3DArrayAligned(w=w, t=t)
                else:
                    self.echo('Remapping local alignment, t: %i, w: %i' % (t, w))
                    if target_is_mrc:
                        des.close()
                    arr = self.get3DArrayRemapped(w=w, t=t)

                if target_is_mrc and des.closed():
                    des.init()
                    des.openFile()

                if min0:
                    arr = N.where(arr > 0, arr, 0)
                    
                des.write3DArr(arr, w=w, t=t)
        des.close()

        return fn


    def saveNonlinearImage(self, out=None, gridStep=10):
        """
        save the result of non-linear transformation into the filename "out"
        gridStep: spacing of grid (number of pixels)

        return out
        """
        if self.mapyx is None:
            return
        
        if not out:
            out = os.path.extsep.join((self.img.filename, 'local'))

        arr = N.zeros(self.mapyx.shape[:3]+self.mapyx.shape[-2:], N.float32)
        for t in xrange(self.nt):
            a = self.img.get3DArr(w=self.refwave, t=t)
            if arr.shape[2] == 1:
                a = N.max(a, 0)
                arr[t,self.refwave,0] = a
            else:
                arr[t,self.refwave] = a
            me = a.max()#
            arr[t,:,:,::gridStep,:] = me#1.
            arr[t,:,:,:,::gridStep] = me#1.
        affine = N.zeros((7,), N.float64)
        affine[-3:] = 1
        
        self.img.close() # to avoid the error (too many open files) on Mac with multiprocessing
        
        canvas = N.empty_like(arr)
        for t in xrange(self.nt):
            for w in xrange(self.nw):
                canvas[t,w] = af.remapWithAffine(arr[t,w], self.mapyx[t,w], affine)
                
        del arr
        self.img = im.load(os.path.join(self.dirname, self.file))
        self.restoreDimFromExtra()
        
        hdr = mrcIO.makeHdr_like(self.hdr)
        hdr.ImgSequence = 2
        hdr.Num[-1] = N.prod(self.mapyx.shape[:3])

        Mrc.save(N.squeeze(canvas), out, hdr=hdr, ifExists='overwrite')
        del canvas
    
        return out
        
