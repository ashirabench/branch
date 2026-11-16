import org.openlca.core.math.rand.NumberGenerator;
import java.util.Arrays;
public class LogNormalCheck {
  static void run(double gm, double gsd) {
    NumberGenerator g = NumberGenerator.logNormal(gm, gsd);
    int n = 1_000_000; double[] x = new double[n]; double s = 0;
    for (int i = 0; i < n; i++) { x[i] = g.next(); s += x[i]; }
    Arrays.sort(x);
    double sig = Math.log(gsd);
    System.out.printf("geometric mean %.3f, gsd %.2f: mean of draws %.4f, median %.4f | gm*exp(-s2/2) = %.4f, gm*exp(+s2/2) = %.4f%n",
      gm, gsd, s / n, x[n / 2], gm * Math.exp(-sig * sig / 2), gm * Math.exp(sig * sig / 2));
  }
  public static void main(String[] a) { run(1.0, 1.2); run(1.0, 1.72); run(-1.0, 1.2); }
}
