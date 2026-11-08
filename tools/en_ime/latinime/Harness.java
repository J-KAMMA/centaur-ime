// AOSP LatinIME の C++ 本体で、打った語の直しの候補を出す（Centaur IME 英語版との比べの計測用）。
//
//   java -cp <classes> Harness <libjni_latinime.so> <entries.tsv>  < 入力 > 出力
// entries.tsv は「u<TAB>語<TAB>0〜255」と「b<TAB>前の語<TAB>語<TAB>0〜255」の行。
// 入力は 1 行に「前の語<TAB>打った語」（文の頭は前の語を空にする）。出力は候補をタブで並べた 1 行。
// 物理キーボードの打鍵として、Android と同じく座標なし（NOT_A_COORDINATE）で渡す。
import com.android.inputmethod.keyboard.ProximityInfo;
import com.android.inputmethod.latin.BinaryDictionary;
import com.android.inputmethod.latin.DicTraverseSession;

import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class Harness {
    static final int MAX_WORD_LENGTH = 48, MAX_RESULTS = 18, MAX_PROXIMITY = 16;
    static final int KEY = 100, GRID_W = 32, GRID_H = 16;
    static final String[] ROWS = {"qwertyuiop", "asdfghjkl", "zxcvbnm"};

    static int[] cps(String s) { return s.codePoints().toArray(); }

    static long proximity() {
        List<int[]> keys = new ArrayList<>(); // x, y, code
        for (int r = 0; r < ROWS.length; r++)
            for (int c = 0; c < ROWS[r].length(); c++)
                keys.add(new int[]{c * KEY + r * KEY / 2, r * KEY, ROWS[r].charAt(c)});
        int width = 10 * KEY, height = 3 * KEY;
        int cellW = (width + GRID_W - 1) / GRID_W, cellH = (height + GRID_H - 1) / GRID_H;
        int threshold = (int) (KEY * 1.2f), th2 = threshold * threshold;
        int[] prox = new int[GRID_W * GRID_H * MAX_PROXIMITY];
        java.util.Arrays.fill(prox, -1);
        for (int gy = 0; gy < GRID_H; gy++)
            for (int gx = 0; gx < GRID_W; gx++) {
                int cx = gx * cellW + cellW / 2, cy = gy * cellH + cellH / 2, n = 0;
                int base = (gy * GRID_W + gx) * MAX_PROXIMITY;
                for (int[] k : keys) {
                    int dx = Math.max(0, Math.max(k[0] - cx, cx - (k[0] + KEY - 1)));
                    int dy = Math.max(0, Math.max(k[1] - cy, cy - (k[1] + KEY - 1)));
                    if (dx * dx + dy * dy < th2 && n < MAX_PROXIMITY) prox[base + n++] = k[2];
                }
            }
        int kc = keys.size();
        int[] xs = new int[kc], ys = new int[kc], ws = new int[kc], hs = new int[kc], codes = new int[kc];
        for (int i = 0; i < kc; i++) {
            xs[i] = keys.get(i)[0]; ys[i] = keys.get(i)[1]; ws[i] = KEY; hs[i] = KEY; codes[i] = keys.get(i)[2];
        }
        return ProximityInfo.setProximityInfoNative(width, height, GRID_W, GRID_H, KEY, KEY, prox, kc,
                xs, ys, ws, hs, codes, null, null, null);
    }

    public static void main(String[] args) throws Exception {
        System.load(args[0]);
        long dict = BinaryDictionary.createOnMemoryNative(403L, "en_US",
                new String[]{"dictionary", "locale", "version", "date"},
                new String[]{"main:en_us", "en_US", "1", "0"});
        if (dict == 0) throw new IllegalStateException("createOnMemory failed");
        int uni = 0, bi = 0;
        try (BufferedReader r = new BufferedReader(new InputStreamReader(new FileInputStream(args[1]), StandardCharsets.UTF_8))) {
            for (String l; (l = r.readLine()) != null; ) {
                String[] p = l.split("\t");
                if (p[0].equals("u")) {
                    if (BinaryDictionary.addUnigramEntryNative(dict, cps(p[1]), Integer.parseInt(p[2]), new int[0], -1,
                            false, false, false, 0)) uni++;
                } else if (p[0].equals("b")) {
                    if (BinaryDictionary.addNgramEntryNative(dict, new int[][]{cps(p[1])}, new boolean[]{false}, cps(p[2]),
                            Integer.parseInt(p[3]), 0)) bi++;
                }
            }
        }
        System.err.println("entries uni=" + uni + " bi=" + bi);
        long pinfo = proximity();
        long session = DicTraverseSession.setDicTraverseSessionNative("en_US", 0L);
        DicTraverseSession.initDicTraverseSessionNative(session, dict, null, 0);
        // 0 ジェスチャー、1 編集距離をすべて使う、2 不適切語を除く、3 空白つきジェスチャー、4 地域の重み（千分率）
        int[] options = {0, 0, 0, 0, 1000, 0};
        PrintStream out = new PrintStream(System.out, true, "UTF-8");
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        for (String l; (l = in.readLine()) != null; ) {
            String[] p = l.split("\t", -1);
            int[] typed = cps(p[1]);
            int n = typed.length;
            int[] x = new int[n], y = new int[n], t = new int[n], ids = new int[n];
            java.util.Arrays.fill(x, -1);
            java.util.Arrays.fill(y, -1);
            int[] input = new int[MAX_WORD_LENGTH];
            System.arraycopy(typed, 0, input, 0, n);
            boolean bos = p[0].isEmpty();
            int[][] prev = {bos ? new int[0] : cps(p[0]), new int[0], new int[0]};
            boolean[] prevBos = {bos, false, false};
            int[] count = new int[1], outCps = new int[MAX_WORD_LENGTH * MAX_RESULTS], scores = new int[MAX_RESULTS],
                    spaces = new int[MAX_RESULTS], types = new int[MAX_RESULTS], conf = new int[1];
            float[] weight = {-1f};
            BinaryDictionary.getSuggestionsNative(dict, pinfo, session, x, y, t, ids, input, n, options,
                    prev, prevBos, 1, count, outCps, scores, spaces, types, conf, weight);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < count[0]; i++) {
                int s = i * MAX_WORD_LENGTH, e = s;
                while (e < s + MAX_WORD_LENGTH && outCps[e] != 0) e++;
                if (i > 0) sb.append('\t');
                sb.append(new String(outCps, s, e - s));
            }
            out.println(sb);
        }
    }
}
