import autograd as ag
import scipy.sparse as sp
import scipy.sparse.linalg as spl
import autograd.numpy as npa
import numpy as np

from ceviche.solvers import solve_linear

""" This file defines the very lowest level sparse matrix primitives that allow autograd to
be compatible with FDFD.  One needs to define the derivatives of Ax = b and x = A^-1 b for sparse A.

This is done using the entries and indices of A, instead of the sparse matrix objects, since autograd doesn't
know how to handle those as arguments to functions.
"""


""" ========================== Helper Functions. ========================== """
# (These may go in utils.py or somewhere else later)

def make_sparse(entries, indices, N):
    """Construct a sparse csc matrix
    Args:
      entries: numpy array with shape (M,) giving values for non-zero
        matrix entries.
      indices: numpy array with shape (2, M) giving x and y indices for
        non-zero matrix entries.
      N: resulting matrix is of shape (N, N)
    Returns:
      sparse, complex, (N, N) matrix with specified values
    """  
    shape = (N, N)
    coo = sp.coo_matrix((entries, indices), shape=shape, dtype=np.complex128)
    return coo.tocsc()

def make_sparse_MxN(entries, indices, shape):
    """Construct a sparse csc matrix
    Args:
      entries: numpy array with shape (M,) giving values for non-zero
        matrix entries.
      indices: numpy array with shape (2, M) giving x and y indices for
        non-zero matrix entries.
      shape: shape of matrix
    Returns:
      sparse, complex, matrix with specified values
    """
    coo = sp.coo_matrix((entries, indices), shape=shape, dtype=np.complex128)
    return coo.tocsc()

def transpose_indices(indices):
    # returns the transposed indices for transpose sparse matrix creation
    return np.flip(indices, axis=0)

def make_rand(N):
    # makes a random vector of size N with elements between -0.5 and 0.5
    return np.random.random(N) - 0.5

def make_rand_complex(N):
    # makes a random complex-valued vector of size N with re and im parts between -0.5 and 0.5
    return make_rand(N) + 1j * make_rand(N)

def make_rand_indeces(N, M):
    # make M random indeces into an NxN matrix
    return np.random.randint(low=0, high=N, size=(2, M))

def make_rand_entries_indices(N, M):
    # make M random indeces and corresponding entries
    entries = make_rand_complex(M)
    indices = make_rand_indeces(N, M)
    return entries, indices

def make_rand_sparse(N, M):
    # make a random sparse matrix of shape '(N, N)' and 'M' non-zero elements
    entries, indices = make_rand_entries_indices(N, M)
    return make_sparse(entries, indices, N)

def der_num(fn, arg, index, delta):
    # numerical derivative of `fn(arg)` with respect to `index` into arg and numerical step size `delta`
    arg_i_for  = arg.copy()
    arg_i_back = arg.copy()
    arg_i_for[index] += delta / 2
    arg_i_back[index] -= delta / 2
    df_darg = (fn(arg_i_for) - fn(arg_i_back)) / delta
    return df_darg

def grad_num(fn, arg, delta=1e-6):
    # take a (complex) numerical derivative of function 'fn' with argument 'arg' with step size 'delta'
    N = arg.size
    grad = np.zeros((N,), dtype=np.complex128)
    f0 = fn(arg)
    for i in range(N):
        grad[i] = der_num(fn, arg, i, delta)        # real part
        grad[i] += der_num(fn, arg, i, 1j * delta)  # imaginary part
    return grad

def get_entries_indices(csr_matrix):
    # takes sparse matrix and returns the entries and indeces in form compatible with 'make_sparse'
    shape = csr_matrix.shape
    coo_matrix = csr_matrix.tocoo()
    entries = csr_matrix.data
    cols = coo_matrix.col
    rows = coo_matrix.row
    indices = np.vstack((rows, cols))
    return entries, indices


""" GUIDE TO THE PRIMITIVES DEFINED BELOW:
        naming convention for gradient functions:
           "def grad_{function_name}_{argument_name}_{mode}"
        defines the derivative of `function_name` with respect to `argument_name` using `mode`-mode differentiation    
        where 'mode' is one of 'reverse' or 'forward'

    These functions define the basic operations needed for FDFD and also their derivatives
    in a form that autograd can understand.
    This allows you to use fdfd classes in autograd functions.
    The code is organized so that autograd never sees sparse matrices in arguments, since it doesn't know how to handle them
    Look but don't touch!

    NOTES for the curious (since this information isnt in autograd documentation...)

        To define a function as being trackable by autograd, need to add the 
        @primitive decorator

    REVERSE MODE
        'vjp' defines the vector-jacobian product for reverse mode (adjoint)
        a vjp_maker function takes as arguments
            1. the output of the @primitive
            2. the rest of the original arguments in the @primitive
        and returns
            a *function* of the backprop vector (v) that defines the operation
            (d{function} / d{argument_i})^T @ v

    FORWARD MODE:
        'jvp' defines the jacobian-vector product for forward mode (FMD)
        a jvp_maker function takes as arguments
            1. the forward propagating vector (g)
            2. the output of the @primitive
            3. the rest of the original arguments in the @primitive
        and returns
            (d{function} / d{argument_i}) @ g

    After this, you need to link the @primitive to its vjp/jvp using
    defvjp(function, arg1's vjp, arg2's vjp, ...)
    defjvp(function, arg1's jvp, arg2's jvp, ...)
"""

""" ========================== Sparse Matrix-Vector Multiplication =========================="""

@ag.primitive
def sp_mult(entries, indices, x):
    """ Multiply a sparse matrix (A) by a dense vector (x)
    Args:
      entries: numpy array with shape (num_non_zeros,) giving values for non-zero
        matrix entries into A.
      indices: numpy array with shape (2, num_non_zeros) giving x and y indices for
        non-zero matrix entries into A.
      x: 1d numpy array specifying the vector to multiply by.
    Returns:
      1d numpy array corresponding to the result (b) of A * x = b.
    """
    A = make_sparse(entries, indices, N=x.size)
    return A.dot(x)

def grad_sp_mult_entries_reverse(ans, entries, indices, x):
    i, j = indices
    def vjp(v):
        return v[i] * x[j]
    return vjp

# def grad_sp_mult_entries_reverse(b, entries, indices, x):
#     """ The complicated way that helped me derive the sparse-sparse primitives """
#     entries_a1 = np.ones(entries.shape)
#     Ma = entries.size
#     a_ik, a_jk = indices
#     indices_D_jka = np.vstack((np.arange(Ma), a_jk))
#     indices_D_ika = np.vstack((np.arange(Ma), a_ik))
#     D_jka = make_sparse_MxN(entries_a1, indices_D_jka, shape=(Ma, x.size))
#     D_ika = make_sparse_MxN(entries_a1, indices_D_ika, shape=(Ma, x.size))
#     D_jka_x = D_jka.dot(x)
#     def vjp(v):
#         D_ika_v = D_ika.dot(v)
#         return D_jka_x * D_ika_v
#     return vjp

def grad_sp_mult_x_reverse(b, entries, indices, x):
    indices_T = transpose_indices(indices)
    def vjp(v):
        return sp_mult(entries, indices_T, v)
    return vjp

ag.extend.defvjp(sp_mult, grad_sp_mult_entries_reverse, None, grad_sp_mult_x_reverse)

def grad_sp_mult_entries_forward(g, b, entries, indices, x):
    return sp_mult(g, indices, x)

def grad_sp_mult_x_forward(g, b, entries, indices, x):
    return sp_mult(entries, indices, g)

ag.extend.defjvp(sp_mult, grad_sp_mult_entries_forward, None, grad_sp_mult_x_forward)


""" ========================== Sparse Matrix-Vector Solve =========================="""

@ag.primitive
def sp_solve(entries, indices, b):
    """ Solve a sparse matrix (A) with source (b)
    Args:
      entries: numpy array with shape (num_non_zeros,) giving values for non-zero
        matrix entries.
      indices: numpy array with shape (2, num_non_zeros) giving x and y indices for
        non-zero matrix entries.
      b: 1d numpy array specifying the source.
    Returns:
      1d numpy array corresponding to the solution of A * x = b.
    """
    A = make_sparse(entries, indices, N=b.size)
    # calls a customizable solving function from ceviche.solvers
    return solve_linear(A, b)

def grad_sp_solve_entries_reverse(ans, entries, indices, b):
    indices_T = transpose_indices(indices)
    i, j = indices
    def vjp(v):
        adj = sp_solve(entries, indices_T, -v)
        return adj[i] * ans[j]
    return vjp

def grad_sp_solve_x_reverse(ans, entries, indices, b):
    indices_T = transpose_indices(indices)
    def vjp(v):
        return sp_solve(entries, indices_T, v)
    return vjp

ag.extend.defvjp(sp_solve, grad_sp_solve_entries_reverse, None, grad_sp_solve_x_reverse)

def grad_sp_solve_entries_forward(g, x, entries, indices, b):
    forward = sp_mult(g, indices, -x)
    return sp_solve(entries, indices, forward)

def grad_sp_solve_x_forward(g, x, entries, indices, b):
    return sp_solve(entries, indices, g)

ag.extend.defjvp(sp_solve, grad_sp_solve_entries_forward, None, grad_sp_solve_x_forward)


""" ==========================Sparse Matrix-Sparse Matrix Multiplication ========================== """

@ag.primitive
def spsp_mult(entries_a, indices_a, entries_x, indices_x, N):
    """ Multiply a sparse matrix (A) by a sparse matrix (X) A @ X = B
    Args:
      entries_a: numpy array with shape (num_non_zeros,) giving values for non-zero
        matrix entries into A.
      indices_a: numpy array with shape (2, num_non_zeros) giving x and y indices for
        non-zero matrix entries into A.
      entries_x: numpy array with shape (num_non_zeros,) giving values for non-zero
        matrix entries into X.
      indices_x: numpy array with shape (2, num_non_zeros) giving x and y indices for
        non-zero matrix entries into X.
      N: all matrices are assumed of shape (N, N) (need to specify because no dense vector supplied)
    Returns:
      entries_b: numpy array with shape (num_non_zeros,) giving values for non-zero
        matrix entries into the result B.
      indices_b: numpy array with shape (2, num_non_zeros) giving i, j indices for
        non-zero matrix entries into the result B.      
    """
    A = make_sparse(entries_a, indices_a, N=N)
    X = make_sparse(entries_x, indices_x, N=N)
    B = A.dot(X)
    entries_b, indices_b = get_entries_indices(B)
    return entries_b, indices_b

def grad_spsp_mult_entries_a_reverse(b_out, entries_a, indices_a, entries_x, indices_x, N):

    # too complicated to explain...
    _, indices_b = b_out
    a_ik, a_jk = indices_a
    b_ik, b_jk = indices_b

    entries_a1 = np.ones(entries_a.shape)
    entries_b1 = np.ones(b_ik.shape)

    Ma = entries_a.size
    Mb = entries_b1.size

    indices_D_ika = np.vstack((np.arange(Ma), a_ik))
    indices_D_jka = np.vstack((np.arange(Ma), a_jk))
    D_ika = make_sparse_MxN(entries_a1, indices_D_ika, shape=(Ma, N))
    D_jka = make_sparse_MxN(entries_a1, indices_D_jka, shape=(Ma, N))

    indices_D_ikb = np.vstack((np.arange(Mb), b_ik))
    indices_D_jkb = np.vstack((np.arange(Mb), b_jk))
    D_ikb = make_sparse_MxN(entries_b1, indices_D_ikb, shape=(Mb, N))
    D_jkb = make_sparse_MxN(entries_b1, indices_D_jkb, shape=(Mb, N))

    X = make_sparse(entries_x, indices_x, N)
    D_jka_X = D_jka.dot(X)

    def vjp(v):
        entries_v, _ = v
        V = make_sparse(entries_v, indices_b, N)
        D_ika_V = D_ika.dot(V)
        combined = D_ika_V.multiply(D_jka_X)
        return combined.sum(axis=1)

    return vjp

def grad_spsp_mult_entries_x_reverse(b_out, entries_a, indices_a, entries_x, indices_x, N):

    entries_b, indices_b = b_out
    indices_aT = transpose_indices(indices_a)
    indices_xT = transpose_indices(indices_x)
    indices_bT = transpose_indices(indices_b)

    b_T_out = entries_b, indices_bT
    vjp_XT_AT = grad_spsp_mult_entries_a_reverse(b_T_out, entries_x, indices_xT, entries_a, indices_aT, N)

    return lambda v: vjp_XT_AT(v)

ag.extend.defvjp(spsp_mult, grad_spsp_mult_entries_a_reverse, None, grad_spsp_mult_entries_x_reverse, None, None)

def grad_spsp_mult_entries_a_forward(g, b_out, entries_a, indices_a, entries_x, indices_x, N):

    _, indices_b = b_out
    a_ik, a_jk = indices_a
    b_ik, b_jk = indices_b

    entries_a1 = np.ones(entries_a.shape)
    entries_b1 = np.ones(b_ik.shape)

    Ma = entries_a.size
    Mb = entries_b1.size

    indices_D_ika = np.vstack((np.arange(Ma), a_ik))
    indices_D_jka = np.vstack((np.arange(Ma), a_jk))
    D_ika = make_sparse_MxN(entries_a1, indices_D_ika, shape=(Ma, N))
    D_jka = make_sparse_MxN(entries_a1, indices_D_jka, shape=(Ma, N))

    indices_D_ikb = np.vstack((np.arange(Mb), b_ik))
    indices_D_jkb = np.vstack((np.arange(Mb), b_jk))
    D_ikb = make_sparse_MxN(entries_b1, indices_D_ikb, shape=(Mb, N))
    D_jkb = make_sparse_MxN(entries_b1, indices_D_jkb, shape=(Mb, N))

    X = make_sparse(entries_x, transpose_indices(indices_a), N)
    G = make_sparse(g, indices_a, N)

    Dx = D_jkb.dot(X)
    Dg = D_ikb.dot(G)

    combined = Dx.multiply(Dg)
    combined_flat = combined.dot(np.ones((N, )))

    return combined_flat, np.zeros((2, Mb))

def grad_spsp_mult_entries_x_forward(g, b_out, entries_a, indices_a, entries_x, indices_x, N):

    entries_b, indices_b = b_out
    indices_aT = transpose_indices(indices_a)
    indices_xT = transpose_indices(indices_x)
    indices_bT = transpose_indices(indices_b)

    b_T_out = entries_b, indices_bT
    return grad_spsp_mult_entries_a_forward(g, b_T_out, entries_x, indices_xT, entries_a, indices_aT, N)

ag.extend.defjvp(spsp_mult, grad_spsp_mult_entries_a_forward, None, grad_spsp_mult_entries_x_forward, None, None)


""" ========================== Nonlinear Solve ========================== """

def sp_solve_nl(parameters, a_indices, b, fn_nl):
    """
        parameters: entries into matrix A are function of parameters and solution x
        a_indices: indices into sparse A matrix
        b: source vector for A(xx = b
        fn_nl: describes how the entries of a depend on the solution of A(x,p) @ x = b and the parameters  `a_entries = fn_nl(params, x)`
    """

    # do the actual nonlinear solve in `_solve_nl_problem` (using newton, picard, whatever)
    # this tells you the final entries into A given the parameters and the nonlinear function.
    a_entries = ceviche.solvers._solve_nl_problem(parameters, a_indices, fn_nl, a_entries0=None)  # optinally, give starting a_entries
    x = sp_solve(a_entries, a_indices, b)  # the final solution to A(x) x = b
    return x

def grad_sp_solve_nl_parameters(x, parameters, a_indices, b, fn_nl):

    """ 
    We are finding the solution (x) to the nonlinear function:

        f = A(x, p) @ x - b = 0

    And need to define the vjp of the solution (x) with respect to the parameters (p)

        vjp(v) = (dx / dp)^T @ v

    To do this (see Eq. 5 of https://pubs-acs-org.stanford.idm.oclc.org/doi/pdf/10.1021/acsphotonics.8b01522)
    we need to solve the following linear system:

        [ df  / dx,  df  / dx*] [ dx  / dp ] = -[ df  / dp]
        [ df* / dx,  df* / dx*] [ dx* / dp ]    [ df* / dp]
    
    Note that we need to explicitly make A a function of x and x* for complex x

    In our case:

        (df / dx)  = (dA / dx) @ x + A
        (df / dx*) = (dA / dx*) @ x
        (df / dp)  = (dA / dp) @ x

    How do we put this into code?  Let

        A(x, p) @ x -> Ax = sp_mult(entries_a(x, p), indices_a, x)

    Since we already defined the primitive of sp_mult, we can just do:

        (dA / dx) @ x -> ag.jacobian(Ax, 0)

    Now how about the source term?

        (dA / dp) @ x -> ag.jacobian(Ax, 1)

    Note that this is a matrix, not a vector. 
    We'll have to handle dA/dx* but this can probably be done, maybe with autograd directly.

    Other than this, assuming entries_a(x, p) is fully autograd compatible, we can get these terms no problem!

    Coming back to our problem, we actually need to compute:

        (dx / dp)^T @ v

    Because

        (dx / dp) = -(df / dx)^{-1} @ (df / dp)

    (ignoring the complex conjugate terms).  We can write this vjp as

        (df / dp)^T @ (df / dx)^{-T} @ v

    Since df / dp is a matrix, not a vector, its more efficient to do the mat_mul on the right first.
    So we first solve

        adjoint(v) = -(df / dx)^{-T} @ v
                   => sp_solve(entries_a_big, transpose(indices_a_big), -v)

    and then it's a simple matter of doing the matrix multiplication

        vjp(v) = (df / dp)^T @ adjoint(v)
               => sp_mult(entries_dfdp, transpose(indices_dfdp), adjoint)

    and then return the result, making sure to strip the complex conjugate.

        return vjp[:N]
    """

    def vjp(v):
        raise NotImplementedError
    return vjp

def grad_sp_solve_nl_b(x, parameters, a_indices, b, fn_nl):

    """ 
    Computing the derivative w.r.t b is simpler

        f = A(x) @ x - b(p) = 0

    And now the terms we need are

        df / dx  = (dA / dx) @ x + A
        df / dx* = (dA / dx*) @ x
        df / dp  = -(db / dp)

    So it's basically the same problem with a differenct source term now.
    """

    def vjp(v):
        raise NotImplementedError
    return vjp

ag.extend.defvjp(sp_solve_nl, grad_sp_solve_nl_parameters, None, grad_sp_solve_nl_b, None)


if __name__ == '__main__':

    """ Testing ground for sparsse-sparse matmul primitives. """

    import ceviche    # use the ceviche wrapper for autograd derivatives
    DECIMAL = 3       # number of decimals to check to

    ## Setup

    N = 5        # size of matrix dimensions.  matrix shape = (N, N)
    M = N**2 - 1     # number of non-zeros (make it dense for numerical stability)

    # these are the default values used within the test functions
    indices_const = make_rand_indeces(N, M)
    entries_const = make_rand_complex(M)
    x_const = make_rand_complex(N)
    b_const = make_rand_complex(N)

    def out_fn(output_vector):
        # this function takes the output of each primitive and returns a real scalar (sort of like the objective function)
        return npa.abs(npa.sum(output_vector))

    def fn_spsp_entries(entries):
        # sparse matrix multiplication (Ax = b) as a function of matrix entries 'A(entries)'
        entries_c, indices_c = spsp_mult(entries_const, indices_const, entries, indices_const, N=N)
        x = sp_solve(entries_c, indices_c, b_const)
        return out_fn(x)

    entries = make_rand_complex(M)

    # doesnt pass yet
    grad_rev = ceviche.jacobian(fn_spsp_entries, mode='reverse')(entries)[0]
    grad_true = grad_num(fn_spsp_entries, entries)
    np.testing.assert_almost_equal(grad_rev, grad_true, decimal=DECIMAL)

    # Testing Gradients of 'Sparse-Sparse Multiply entries Forward-mode'

    grad_for = ceviche.jacobian(fn_spsp_entries, mode='forward')(entries)[0]
    grad_true = grad_num(fn_spsp_entries, entries)
    np.testing.assert_almost_equal(grad_for, grad_true, decimal=DECIMAL)

    ## TESTS SPARSE MATRX CREATION

    A = make_rand_sparse(N, M)
    B = make_rand_sparse(N, M)
    C_true = A.dot(B).todense()

    ae, ai = get_entries_indices(A)
    be, bi = get_entries_indices(B)
    ce, ci = spsp_mult(ae, ai, be, bi, N)

    C_test = make_sparse(ce, ci, N).todense()

    np.testing.assert_almost_equal(C_true, C_test, decimal=DECIMAL)

