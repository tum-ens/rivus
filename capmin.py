import coopr.pyomo as pyomo
import networkx as nx
import numpy as np

def create_model(filename):
    """Return a CAPMIN model instance from input file 
    m = pyomo.ConcreteModel()
    m.name = 'CAPMIN'
    
