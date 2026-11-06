// word_tracker の試験（小さな表で、境目を中心に）。
//   g++ -std=c++17 core.cc word_tracker.cc word_tracker_test.cc && ./a.out
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>

#include "core.h"
#include "word_tracker.h"

namespace {

int failures = 0;

void Check(bool ok, const char* what, int line) {
  if (!ok) {
    std::printf("NG line %d: %s\n", line, what);
    ++failures;
  }
}
#define CHECK(x) Check((x), #x, __LINE__)

void Type(centaur::WordTracker* t, const char32_t* s) {
  for (; *s; ++s) t->OnChar(*s);
}

}  // namespace

int main() {
  const char* path = "word_tracker_test_table.tsv";
  {
    std::ofstream f(path);
    f << "U\tthe\t100\nU\tthere\t20\nU\ttherefore\t5\nU\tthink\t30\nU\tthinking\t10\nU\tdon't\t8\n"
         "U\tmeeting\t12\nU\tmeet\t9\nU\ti\t50\n"
         "B\t<s>\tthe\t40\nB\tthe\tmeeting\t6\nB\ti\tthink\t20\nB\tthink\tthe\t3\n";
  }
  centaur::Model m;
  CHECK(m.Load(path));
  std::remove(path);

  {
    centaur::WordTracker t(&m);
    CHECK(t.Completion().empty());  // 何も打っていない
    Type(&t, U"t");
    CHECK(t.Completion().empty());  // 1 字では出さない
    Type(&t, U"h");
    CHECK(t.Completion() == U"the" || t.Completion().empty());  // the は打った字より長くないので出ない
    Type(&t, U"i");
    CHECK(t.Completion() == U"think");
    CHECK(t.TabInsert() == U"nk");
    t.OnCompletionInserted();
    CHECK(t.word() == U"think");
    t.OnChar(U' ');
    CHECK(t.prev() == U"think");
    CHECK(t.word().empty());
  }
  {
    // 大文字・小文字を打ったとおりに合わせる
    centaur::WordTracker t(&m);
    Type(&t, U"Thi");
    CHECK(t.Completion() == U"Think");
    centaur::WordTracker u(&m);
    Type(&u, U"THI");
    CHECK(u.Completion() == U"THINK");
  }
  {
    // 前の語で選ぶ: 「the me」→ meeting（the meeting の並びがある）
    centaur::WordTracker t(&m);
    Type(&t, U"the me");
    CHECK(t.prev() == U"the");
    CHECK(t.Completion() == U"meeting");
  }
  {
    // 文の終わりで前の語を文の頭に戻す
    centaur::WordTracker t(&m);
    Type(&t, U"i think. ");
    CHECK(t.prev() == U"<s>");
  }
  {
    // Backspace: 語の中は 1 字戻す。語の外では追跡をやめ、次の区切りまで候補を出さない
    centaur::WordTracker t(&m);
    Type(&t, U"thin");
    t.OnBackspace();
    CHECK(t.word() == U"thi");
    t.OnBackspace();
    t.OnBackspace();
    t.OnBackspace();
    CHECK(t.word().empty());
    t.OnBackspace();  // 語の外
    Type(&t, U"thi");
    CHECK(t.Completion().empty());
    t.OnChar(U' ');
    Type(&t, U"thi");
    CHECK(t.Completion() == U"think");
  }
  {
    // カーソルが動いたら、前の語は分からない
    centaur::WordTracker t(&m);
    Type(&t, U"the ");
    t.Reset();
    CHECK(t.prev() == U"<s>");
    Type(&t, U"me");
    CHECK(t.Completion().empty());
  }
  {
    // ' を含む語
    centaur::WordTracker t(&m);
    Type(&t, U"don");
    CHECK(t.Completion() == U"don't");
  }
  {
    // 直し: 表にある語は直さない。無い語は候補を出す（勝手には替えない）
    centaur::WordTracker t(&m);
    Type(&t, U"think");
    CHECK(t.Corrections().empty());
    centaur::WordTracker u(&m);
    Type(&u, U"thnik");
    CHECK(!u.Corrections().empty() && u.Corrections()[0] == U"think");
    centaur::WordTracker v(&m);
    Type(&v, U"th");
    CHECK(v.Corrections().empty());  // 2 字では直さない
  }
  {
    // 表が無いとき
    centaur::WordTracker t(nullptr);
    Type(&t, U"thi");
    CHECK(t.Completion().empty());
    CHECK(t.Corrections().empty());
    CHECK(t.TabInsert().empty());
  }
  {
    // ブランド名の正式な書き方（github → GitHub）
    const char* tpath = "word_tracker_test_brand.tsv";
    const char* cpath = "word_tracker_test_casing.tsv";
    {
      std::ofstream f(tpath);
      f << "U\tgithub\t30\nU\tgit\t5\nU\tthe\t100\nB\tthe\tgithub\t3\n";
      std::ofstream g(cpath);
      g << "# typed<TAB>official\ngithub\tGitHub\ngit\t-\n";
    }
    centaur::Model b;
    CHECK(b.Load(tpath));
    CHECK(b.LoadCasing(cpath));
    std::remove(tpath);
    std::remove(cpath);
    CHECK(b.Cased(U"github") == U"GitHub");
    CHECK(b.Cased(U"git").empty());  // 「-」は打ったまま
    centaur::WordTracker t(&b);
    Type(&t, U"gith");
    CHECK(t.Completion() == U"GitHub");
    CHECK(t.TabInsert().empty());            // 打った所の大文字が変わるので足すだけにしない
    CHECK(t.TabReplacement() == U"GitHub");  // 語ごと入れ替える
    centaur::WordTracker u(&b);
    Type(&u, U"GITH");
    CHECK(u.Completion() == U"GITHUB");      // 全部大文字なら全部大文字のまま
    CHECK(u.TabInsert() == U"UB");
    CHECK(u.TabReplacement().empty());
    centaur::WordTracker v(&b);
    Type(&v, U"GitH");
    CHECK(v.Completion() == U"GitHub");
    CHECK(v.TabInsert() == U"ub");           // 打った所がそのまま正式な形の頭なら足すだけ
    centaur::WordTracker w(&b);
    Type(&w, U"github");
    CHECK(w.Corrections().size() == 1 && w.Corrections()[0] == U"GitHub");  // 打ち終えた語は見せるだけ
    centaur::WordTracker x(&b);
    Type(&x, U"GitHub");
    CHECK(x.Corrections().empty());          // もう正式な形なら出さない
  }
  std::printf("%s (%d)\n", failures ? "NG" : "OK", failures);
  return failures ? 1 : 0;
}
