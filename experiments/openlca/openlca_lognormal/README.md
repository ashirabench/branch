# How openLCA draws a lognormal value

A minimal check of two facts that the paper states about the Monte Carlo simulation of openLCA 2.6.2. It calls the generator of the library that ships inside the application (`olca-core-2.6.2.jar`, in `openLCA.app/Contents/Eclipse/plugins/olca-app_2.6.2/libs/`), one million draws each.

```
javac -cp olca-core-2.6.2.jar LogNormalCheck.java
java -cp .:olca-core-2.6.2.jar:commons-math3-3.6.1.jar LogNormalCheck
```

Output on 16 November 2026:

```
geometric mean 1.000, gsd 1.20: mean of draws 1.0001, median 0.9834 | gm*exp(-s2/2) = 0.9835, gm*exp(+s2/2) = 1.0168
geometric mean 1.000, gsd 1.72: mean of draws 0.9990, median 0.8631 | gm*exp(-s2/2) = 0.8632, gm*exp(+s2/2) = 1.1584
geometric mean -1.000, gsd 1.20: mean of draws -1.0000, median -0.9836 | gm*exp(-s2/2) = -0.9835, gm*exp(+s2/2) = -1.0168
```

1. The value entered as geometric mean is the arithmetic mean of the draws; their median is that value times exp(-sigma^2 / 2), with sigma the logarithm of the geometric standard deviation. A user asked about this on ask.openLCA (question 9978, "Geometric Mean in parameter uncertainty treated as arithmetic mean?").
2. A negative geometric mean gives negative draws. In a database whose waste outputs carry a negative geometric mean beside a positive amount, a simulation therefore subtracts the treatment of waste that a calculation adds. GreenDelta confirmed this for ecoinvent 3.9.1 in June 2023 as an error of the database (ask.openLCA, question 6159). The copy of BAFU:2026 v1.1 for openLCA that I use has the same pattern in 14,167 waste outputs.
