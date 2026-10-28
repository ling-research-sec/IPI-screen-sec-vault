package lab.ipi.surface
import lab.ipi.surface.data.TextCodec
import org.junit.Assert.*
import org.junit.Test
class TextCodecTest {
    @Test fun csvQuotesAndMultiline() { assertEquals("\"中,文\n\"\"quoted\"\"\"", TextCodec.csv("中,文\n\"quoted\"")) }
    @Test fun csvGuardsFormulas() { assertEquals("\"'=1+1\"", TextCodec.csv("=1+1")); assertEquals("\"' @SUM(A1)\"", TextCodec.csv(" @SUM(A1)")) }
    @Test fun htmlEscapesRatherThanExecutes() { assertEquals("&lt;script&gt;&amp;&quot;&#39;", TextCodec.html("<script>&\"'")) }
    @Test fun filenamesHaveNoTraversal() { assertFalse(TextCodec.filename("../../中文\\file\n").contains('/')); assertFalse(TextCodec.filename("a\\b").contains('\\')); assertEquals("experiment", TextCodec.filename("  ")) }
}
