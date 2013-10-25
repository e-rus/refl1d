import inspect

from numpy import real, imag

from bumps.parameter import Parameter
from refl1d.model import Layer
from refl1d import util

class FunctionProfile(Layer):
    """
    Generic profile function

    Parameters:

        *thickness* the thickness of the layer
        *interface* the roughness of the surface [not implemented]
        *profile* the profile function, suitably parameterized

    The profile function takes a depth z and returns a density rho.

    Fitting parameters are the available named arguments to the function.
    The first argument must be *z*, which is the array of depths at which
    the profile is to be evaluated.  It is guaranteed to be increasing, with
    step size 2*z[0].

    Initial values for the function parameters can be given using name=value.
    These values can be scalars or fitting parameters.  The function will
    be called with the current parameter values as arguments.  The layer
    thickness can be computed as :func:`layer_thickness`.
    """
    # TODO: test that thickness(z) matches the thickness of the layer
    def __init__(self, thickness=0, interface=0, profile=None, name=None, **kw):
        if interface != 0: raise NotImplementedError("interface not yet supported")
        if profile is None:
            raise TypeError("Need profile")
        self.name = name if name else "Profile"
        self.thickness = Parameter.default(thickness, name=name+" thickness")
        self.interface = Parameter.default(interface, name=name+" interface")
        self.profile = profile

        # Query profile function for the list of arguments
        vars = inspect.getargspec(profile)[0]
        #print "vars",vars
        if inspect.ismethod(profile): vars = vars[1:]  # Chop self
        vars = vars[1:]  # Chop z
        #print vars
        unused = [k for k in kw.keys() if k not in vars]
        if len(unused) > 0:
            raise TypeError("Profile got unexpected keyword argument '%s'"%unused[0])
        dups = [k for k in vars
                if k in ('thickness','interface','profile')]
        if len(dups) > 0:
            raise TypeError("Profile has conflicting argument %r"%dups[0])
        for k in vars: kw.setdefault(k,0)
        for k,v in kw.items():
            setattr(self,k,Parameter.default(v,name=name+" "+k))

        self._parameters = vars

    def parameters(self):
        P = dict( (k,getattr(self,k)) for k in self._parameters)
        P['thickness'] = self.thickness
        #P['interface'] = self.interface
        return P

    def render(self, probe, slabs):
        Pw,Pz = slabs.microslabs(self.thickness.value)
        if len(Pw)== 0: return
        kw = dict((k,getattr(self,k).value) for k in self._parameters)
        #print kw
        phi = self.profile(Pz,**kw)
        if phi.shape != Pz.shape:
            raise TypeError("profile function '%s' did not return array phi(z)"
                            %self.profile.__name__)
        Pw,phi = util.merge_ends(Pw, phi, tol=1e-3)
        #P = M*phi + S*(1-phi)
        slabs.extend(rho = [real(phi)], irho = [imag(phi)], w = Pw)
        #slabs.interface(self.interface.value)