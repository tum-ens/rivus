.. urbs documentation master file, created by
   sphinx-quickstart on Wed Sep 10 11:43:04 2014.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.
   
.. module:: rivus

rivus: A mixed integer linear optimisation model for energy infrastructure networks
===================================================================================

:Author: Johannes Dorfner, <johannes.dorfner@tum.de>
:Organization: `Institute for Renewable and Sustainable Energy Systems`_,
               Technische Universität München
:Version: |version|
:Date: |today|
:Copyright:
  This documentation is licensed under a `Creative Commons Attribution 4.0 
  International`__ license.

.. __: http://creativecommons.org/licenses/by/4.0/


Overview
--------

* `rivus`_  is a mixed integer linear programming model for multi-commodity 
  energy infrastructure networks systems with a focus on high spatial 
  resolution.
* It finds the minimum cost energy infrastructure networks to satisfy a given 
  energy distribution for possibly multiple commodities (e.g. electricity, 
  heating, cooling, ...).
* Time is represented by a (small) set of weighted time steps that represent 
  peak or typical loads  
* Spatial data can be provided in form of shapefiles, while technical 
  parameters can be edited in a spreadsheet.
* `urbs`_

Changes
-------

Version 0.1
^^^^^^^^^^^

* Initial release.


Screenshots
-----------

This is a typical result plot created by :func:`rivus.result_figures`, which
in turn is a wrapper around :func:`rivus.plot`, for an exemplary network
structure for electricity (yellow), heat (red) and gas (brown) network. 
Triangles represent energy conversion processes; triangles pointing upwards
indicate generation, downwards indicates consumption of that commodity. The two
diamond shapes in the south (electricity) and east (gas) represent energy
sources.

.. image:: img/caps-elec.*
   :width: 95%
   :align: center

.. image:: img/caps-heat.*
   :width: 95%
   :align: center

.. image:: img/caps-gas.*
   :width: 95%
   :align: center


Dependencies
------------

* `coopr`_ interface to optimisation solvers (CPLEX, GLPK, Gurobi, ...).
  At least one supported solver by coopr must be installed.
* `matplotlib`_ for plotting
* `pandas`_ for input and result data handling, report generation 
* `pyomo`_ for the model equations

   
.. _coopr: https://software.sandia.gov/trac/coopr
.. _Institute for Renewable and Sustainable Energy Systems: http://www.ens.ei.tum.de/
.. _matplotlib: http://matplotlib.org
.. _pandas: https://pandas.pydata.org
.. _pyomo: https://software.sandia.gov/trac/coopr/wiki/Pyomo
.. _rivus: https://github.com/ojdo/rivus
.. _urbs: https://github.com/tum-ens/urbs

