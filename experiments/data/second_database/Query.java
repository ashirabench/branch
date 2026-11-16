import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Statement;

/** Runs SQL statements on an unpacked openLCA database (Apache Derby) and prints tab separated rows.
 *  A line with two dashes ends the rows of each statement. Used by read_elcd.py. */
public class Query {
  public static void main(String[] a) throws Exception {
    try (Connection c = DriverManager.getConnection("jdbc:derby:" + a[0])) {
      for (int i = 1; i < a.length; i++) {
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery(a[i])) {
          ResultSetMetaData m = r.getMetaData();
          int n = m.getColumnCount();
          while (r.next()) {
            StringBuilder b = new StringBuilder();
            for (int k = 1; k <= n; k++) {
              if (k > 1) b.append('\t');
              String v = r.getString(k);
              b.append(v == null ? "" : v.replace('\t', ' ').replace('\n', ' '));
            }
            System.out.println(b);
          }
        }
        System.out.println("--");
      }
    }
  }
}
