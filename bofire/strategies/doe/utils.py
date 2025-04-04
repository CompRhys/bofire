import sys
from itertools import combinations
from typing import List, Optional, Union

import numpy as np
import pandas as pd
from formulaic import Formula
from scipy.optimize import LinearConstraint, NonlinearConstraint

from bofire.data_models.constraints.api import (
    Constraint,
    InterpointEqualityConstraint,
    LinearEqualityConstraint,
    LinearInequalityConstraint,
    NChooseKConstraint,
    NonlinearEqualityConstraint,
    NonlinearInequalityConstraint,
)
from bofire.data_models.domain.domain import Domain
from bofire.data_models.features.continuous import ContinuousInput
from bofire.data_models.strategies.api import RandomStrategy as RandomStrategyDataModel
from bofire.strategies.random import RandomStrategy


def get_formula_from_string(
    model_type: Union[str, Formula] = "linear",
    domain: Optional[Domain] = None,
    rhs_only: bool = True,
) -> Formula:
    """Reformulates a string describing a model or certain keywords as Formula objects.

    Args:
        model_type (str or Formula): A formula containing all model terms.
        domain (Domain): A domain that nests necessary information on
        how to translate a problem to a formula. Contains a problem.
        rhs_only (bool): The function returns only the right hand side of the formula if set to True.

    Returns:
    A Formula object describing the model that was given as string or keyword.

    """
    # set maximum recursion depth to higher value
    recursion_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(2000)

    if isinstance(model_type, Formula):
        return model_type
        # build model if a keyword and a problem are given.
    # linear model
    if model_type == "linear":
        formula = linear_formula(domain)

    # linear and interactions model
    elif model_type == "linear-and-quadratic":
        formula = linear_and_quadratic_formula(domain)

    # linear and quadratic model
    elif model_type == "linear-and-interactions":
        formula = linear_and_interactions_formula(domain)

    # fully quadratic model
    elif model_type == "fully-quadratic":
        formula = fully_quadratic_formula(domain)

    else:
        formula = model_type + "   "

    formula = Formula(formula[:-3])

    if rhs_only:
        if hasattr(formula, "rhs"):
            formula = formula.rhs

    # set recursion limit to old value
    sys.setrecursionlimit(recursion_limit)

    return formula


def linear_formula(
    domain: Optional[Domain],
) -> str:
    """Reformulates a string describing a linear-model or certain keywords as Formula objects.
        formula = model_type + "   "

    Args: domain (Domain): A problem context that nests necessary information on
        how to translate a problem to a formula. Contains a problem.

    Returns:
        A string describing the model that was given as string or keyword.

    """
    assert (
        domain is not None
    ), "If the model is described by a keyword a domain must be provided"
    formula = "".join([input.key + " + " for input in domain.inputs])
    return formula


def linear_and_quadratic_formula(
    domain: Optional[Domain],
) -> str:
    """Reformulates a string describing a linear-and-quadratic model or certain keywords as Formula objects.

    Args: domain (Domain): A problem context that nests necessary information on
        how to translate a problem to a formula. Contains a problem.

    Returns:
        A string describing the model that was given as string or keyword.

    """
    assert (
        domain is not None
    ), "If the model is described by a keyword a problem must be provided."
    formula = "".join([input.key + " + " for input in domain.inputs])
    formula += "".join(["{" + input.key + "**2} + " for input in domain.inputs])
    return formula


def linear_and_interactions_formula(
    domain: Optional[Domain],
) -> str:
    """Reformulates a string describing a linear-and-interactions model or certain keywords as Formula objects.

    Args: domain (Domain): A problem context that nests necessary information on
        how to translate a problem to a formula. Contains a problem.

    Returns:
        A string describing the model that was given as string or keyword.

    """
    assert (
        domain is not None
    ), "If the model is described by a keyword a problem must be provided."
    formula = "".join([input.key + " + " for input in domain.inputs])
    for i in range(len(domain.inputs)):
        for j in range(i):
            formula += (
                domain.inputs.get_keys()[j] + ":" + domain.inputs.get_keys()[i] + " + "
            )
    return formula


def fully_quadratic_formula(
    domain: Optional[Domain],
) -> str:
    """Reformulates a string describing a fully-quadratic model or certain keywords as Formula objects.

    Args: domain (Domain): A problem context that nests necessary information on
        how to translate a problem to a formula. Contains a problem.

    Returns:
        A string describing the model that was given as string or keyword.

    """
    assert (
        domain is not None
    ), "If the model is described by a keyword a problem must be provided."
    formula = "".join([input.key + " + " for input in domain.inputs])
    for i in range(len(domain.inputs)):
        for j in range(i):
            formula += (
                domain.inputs.get_keys()[j] + ":" + domain.inputs.get_keys()[i] + " + "
            )
    formula += "".join(["{" + input.key + "**2} + " for input in domain.inputs])
    return formula


def n_zero_eigvals(
    domain: Domain,
    model_type: Union[str, Formula],
    epsilon=1e-7,
) -> int:
    """Determine the number of eigenvalues of the information matrix that are necessarily zero because of
    equality constraints.
    """
    # sample points (fulfilling the constraints)
    model_formula = get_formula_from_string(
        model_type=model_type,
        rhs_only=True,
        domain=domain,
    )
    N = len(model_formula) + 3

    sampler = RandomStrategy(data_model=RandomStrategyDataModel(domain=domain))
    X = sampler.ask(N)
    # compute eigenvalues of information matrix
    A = model_formula.get_model_matrix(X)
    eigvals = np.abs(np.linalg.eigvalsh(A.T @ A))

    return len(eigvals) - len(eigvals[eigvals > epsilon])


def constraints_as_scipy_constraints(
    domain: Domain,
    n_experiments: int,
    ignore_nchoosek: bool = True,
) -> List:
    """Formulates bofire constraints as scipy constraints.

    Args:
        domain (Domain): Domain whose constraints should be formulated as scipy constraints.
        n_experiments (int): Number of instances of inputs for problem that are evaluated together.
        ingore_nchoosek (bool): NChooseK constraints are ignored if set to true. Defaults to True.

    Returns:
        A list of scipy constraints corresponding to the constraints of the given opti problem.

    """
    # reformulate constraints
    constraints = []
    if len(domain.constraints) == 0:
        return constraints
    for c in domain.constraints:
        if isinstance(c, LinearEqualityConstraint) or isinstance(
            c,
            LinearInequalityConstraint,
        ):
            A, lb, ub = get_constraint_function_and_bounds(c, domain, n_experiments)
            constraints.append(LinearConstraint(A, lb, ub))

        elif isinstance(c, NonlinearEqualityConstraint) or isinstance(
            c,
            NonlinearInequalityConstraint,
        ):
            fun, lb, ub = get_constraint_function_and_bounds(c, domain, n_experiments)
            if c.jacobian_expression is not None:
                constraints.append(NonlinearConstraint(fun, lb, ub, jac=fun.jacobian))
            else:
                constraints.append(NonlinearConstraint(fun, lb, ub))

        elif isinstance(c, NChooseKConstraint):
            if ignore_nchoosek:
                pass
            else:
                fun, lb, ub = get_constraint_function_and_bounds(
                    c,
                    domain,
                    n_experiments,
                )
                constraints.append(NonlinearConstraint(fun, lb, ub, jac=fun.jacobian))

        elif isinstance(c, InterpointEqualityConstraint):
            A, lb, ub = get_constraint_function_and_bounds(c, domain, n_experiments)
            constraints.append(LinearConstraint(A, lb, ub))

        else:
            raise NotImplementedError(f"No implementation for this constraint: {c}")

    return constraints


def get_constraint_function_and_bounds(
    c: Constraint,
    domain: Domain,
    n_experiments: int,
) -> List:
    """Returns the function definition and bounds for a given constraint and domain.

    Args:
        c (Constraint): Constraint for which the constraint matrix should be determined.
        domain (Domain): Domain for which the constraint matrix should be determined.
        n_experiments (int): Number of experiments for which the constraint matrix should be determined.

    Returns:
        A list containing the constraint defining function and the lower and upper bounds.

    """
    D = len(domain.inputs)

    if isinstance(c, LinearEqualityConstraint) or isinstance(
        c,
        LinearInequalityConstraint,
    ):
        # write constraint as matrix
        lhs = {
            c.features[i]: c.coefficients[i] / np.linalg.norm(c.coefficients)
            for i in range(len(c.features))
        }
        row = np.zeros(D)
        for i, name in enumerate(domain.inputs.get_keys()):
            if name in lhs:
                row[i] = lhs[name]

        A = np.zeros(shape=(n_experiments, D * n_experiments))
        for i in range(n_experiments):
            A[i, i * D : (i + 1) * D] = row

        # write upper/lower bound as vector
        lb = -np.inf * np.ones(n_experiments)
        ub = np.ones(n_experiments) * (c.rhs / np.linalg.norm(c.coefficients))
        if isinstance(c, LinearEqualityConstraint):
            lb = np.ones(n_experiments) * (c.rhs / np.linalg.norm(c.coefficients))

        return [A, lb, ub]

    if isinstance(c, NonlinearEqualityConstraint) or isinstance(
        c,
        NonlinearInequalityConstraint,
    ):
        # define constraint evaluation (and gradient if provided)
        fun = ConstraintWrapper(
            constraint=c,
            domain=domain,
            n_experiments=n_experiments,  # type: ignore
        )

        # write upper/lower bound as vector
        lb = -np.inf * np.ones(n_experiments)
        ub = np.zeros(n_experiments)
        if isinstance(c, NonlinearEqualityConstraint):
            lb = np.zeros(n_experiments)

        return [fun, lb, ub]

    if isinstance(c, NChooseKConstraint):
        # define constraint evaluation (and gradient if provided)
        fun = ConstraintWrapper(
            constraint=c,
            domain=domain,
            n_experiments=n_experiments,  # type: ignore
        )

        # write upper/lower bound as vector
        lb = -np.inf * np.ones(n_experiments)
        ub = np.zeros(n_experiments)

        return [fun, lb, ub]

    if isinstance(c, InterpointEqualityConstraint):
        # write lower/upper bound as vector
        multiplicity = c.multiplicity or len(domain.inputs)
        n_batches = int(np.ceil(n_experiments / multiplicity))
        lb = np.zeros(n_batches * (multiplicity - 1))
        ub = np.zeros(n_batches * (multiplicity - 1))

        # write constraint as matrix
        feature_idx = 0
        if c.feature not in domain.inputs.get_keys():
            raise ValueError(f"Feature {c.feature} is not part of the domain {domain}.")
        for i, name in enumerate(domain.inputs.get_keys()):
            if name == c.feature:
                feature_idx = i

        A = np.zeros(shape=(n_batches * (multiplicity - 1), D * n_experiments))
        for batch in range(n_batches):
            for i in range(multiplicity - 1):
                if batch * multiplicity + i + 2 <= n_experiments:
                    A[
                        batch * (multiplicity - 1) + i,
                        batch * multiplicity * D + feature_idx,
                    ] = 1.0
                    A[
                        batch * (multiplicity - 1) + i,
                        (batch * multiplicity + i + 1) * D + feature_idx,
                    ] = -1.0

        # remove overflow in last batch
        if (n_experiments % multiplicity) != 0:
            n_overflow = multiplicity - (n_experiments % multiplicity)
            A = A[:-n_overflow, :]
            lb = lb[:-n_overflow]
            ub = ub[:-n_overflow]

        return [A, lb, ub]

    raise NotImplementedError(f"No implementation for this constraint: {c}")


class ConstraintWrapper:
    """Wrapper for nonlinear constraints."""

    def __init__(
        self,
        constraint: NonlinearConstraint,
        domain: Domain,
        n_experiments: int = 0,
    ) -> None:
        """Args:
        constraint (Constraint): constraint to be called
        domain (Domain): Domain the constraint belongs to
        """
        self.constraint = constraint
        self.names = domain.inputs.get_keys()
        self.D = len(domain.inputs)
        self.n_experiments = n_experiments
        if constraint.features is None:  # type: ignore
            raise ValueError(
                f"The features attribute of constraint {constraint} is not set, but has to be set.",
            )
        self.constraint_feature_indices = np.searchsorted(
            self.names,
            self.constraint.features,  # type: ignore
        )

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """Call constraint with flattened numpy array."""
        x = pd.DataFrame(x.reshape(len(x) // self.D, self.D), columns=self.names)  # type: ignore
        violation = self.constraint(x).to_numpy()  # type: ignore
        violation[np.abs(violation) < 0] = 0
        return violation

    def jacobian(self, x: np.ndarray) -> np.ndarray:
        """Call constraint gradient with flattened numpy array."""
        x = pd.DataFrame(x.reshape(len(x) // self.D, self.D), columns=self.names)  # type: ignore
        gradient_compressed = self.constraint.jacobian(x).to_numpy()  # type: ignore

        jacobian = np.zeros(shape=(self.n_experiments, self.D * self.n_experiments))
        rows = np.repeat(
            np.arange(self.n_experiments),
            len(self.constraint_feature_indices),
        )
        cols = np.repeat(
            self.D * np.arange(self.n_experiments),
            len(self.constraint_feature_indices),
        ).reshape((self.n_experiments, len(self.constraint_feature_indices)))
        cols = (cols + self.constraint_feature_indices).flatten()

        jacobian[rows, cols] = gradient_compressed.flatten()

        return jacobian


def check_nchoosek_constraints_as_bounds(domain: Domain) -> None:
    """Checks if NChooseK constraints of domain can be formulated as bounds.

    Args:
        domain (Domain): Domain whose NChooseK constraints should be checked

    """
    # collect NChooseK constraints
    if len(domain.constraints) == 0:
        return

    nchoosek_constraints = []
    for c in domain.constraints:
        if isinstance(c, NChooseKConstraint):
            nchoosek_constraints.append(c)

    if len(nchoosek_constraints) == 0:
        return

    # check if the domains of all NChooseK constraints are compatible to linearization
    for c in nchoosek_constraints:
        for name in np.unique(c.features):
            input = domain.inputs.get_by_key(name)
            if input.bounds[0] > 0 or input.bounds[1] < 0:  # type: ignore
                raise ValueError(
                    f"Constraint {c} cannot be formulated as bounds. 0 must be inside the \
                    domain of the affected decision variables.",
                )

    # check if the parameter names of two nchoose overlap
    for c in nchoosek_constraints:
        for _c in nchoosek_constraints:
            if c != _c:
                for name in c.features:
                    if name in _c.features:
                        raise ValueError(
                            f"Domain {domain} cannot be used for formulation as bounds. \
                            names attribute of NChooseK constraints must be pairwise disjoint.",
                        )


def nchoosek_constraints_as_bounds(
    domain: Domain,
    n_experiments: int,
) -> List:
    """Determines the box bounds for the decision variables

    Args:
        domain (Domain): Domain to find the bounds for.
        n_experiments (int): number of experiments for the design to be determined.

    Returns:
        A list of tuples containing bounds that respect NChooseK constraint imposed
        onto the decision variables.

    """
    check_nchoosek_constraints_as_bounds(domain)

    # bounds without NChooseK constraints
    bounds = np.array(
        [p.bounds for p in domain.inputs.get(ContinuousInput)] * n_experiments,  # type: ignore
    )

    if len(domain.constraints) > 0:
        for constraint in domain.constraints:
            if isinstance(constraint, NChooseKConstraint):
                n_inactive = len(constraint.features) - constraint.max_count
                if n_inactive > 0:
                    # find indices of constraint.names in names
                    ind = [
                        i
                        for i, p in enumerate(domain.inputs.get_keys())
                        if p in constraint.features
                    ]

                    # find and shuffle all combinations of elements of ind of length max_active
                    ind = np.array(list(combinations(ind, r=n_inactive)))
                    np.random.shuffle(ind)

                    # set bounds to zero in each experiments for the variables that should be inactive
                    for i in range(n_experiments):
                        ind_vanish = ind[i % len(ind)]
                        bounds[ind_vanish + i * len(domain.inputs), :] = [0, 0]
                        if i % len(ind) == len(ind) - 1:
                            np.random.shuffle(ind)
    else:
        pass

    # convert bounds to list of tuples
    bounds = [(b[0], b[1]) for b in bounds]

    return bounds
