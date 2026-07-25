# -*- coding: utf-8 -*-
"""
Fry Sight Words 1000語のフォニックス「トリッキー判定」を機械的に生成するスクリプト。
CMU Pronouncing Dictionary (pronouncing パッケージ) を使い、
基本フォニックスルールとのズレを検出する。
"""
import json
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pronouncing

VOWELS = set("aeiou")

# ARPAbet phoneme -> ざっくりカタカナ (noteの説明文用、精密さは求めない)
KANA = {
    'AA': 'ア', 'AE': 'ア', 'AH': 'ア(あいまい)', 'AO': 'オ', 'AW': 'アウ',
    'AY': 'アイ', 'EH': 'エ', 'ER': 'アー', 'EY': 'エイ', 'IH': 'イ',
    'IY': 'イー', 'OW': 'オウ', 'OY': 'オイ', 'UH': 'ウ', 'UW': 'ウー',
}

def strip_stress(phones):
    return [re.sub(r'\d', '', p) for p in phones.split()]

def get_phones(word):
    """単語の発音(音素リスト、ストレス数字なし)。見つからなければNone"""
    plist = pronouncing.phones_for_word(word.lower())
    if not plist:
        return None
    return strip_stress(plist[0])

def has_phone(phones, target):
    return target in phones

MAGIC_E_EXPECT = {
    'a': ('EY', 'エイ'),
    'e': ('IY', 'イー'),
    'i': ('AY', 'アイ'),
    'o': ('OW', 'オウ'),
    'u': ('UW', 'ウー'),
}

DIGRAPH_EXPECT = {
    'ai': ('EY', 'エイ'),
    'ee': ('IY', 'イー'),
    'oa': ('OW', 'オウ'),
    'ea': ('IY', 'イー'),
    'oi': ('OY', 'オイ'),
    'oy': ('OY', 'オイ'),
    'au': ('AO', 'オー'),
    'aw': ('AO', 'オー'),
    'ay': ('EY', 'エイ'),
    'ou': ('AW', 'アウ'),
    'ey': ('EY', 'エイ'),
    'ei': ('EY', 'エイ'),
    'eo': ('IY', 'イー'),
}

# owはcow型(AW)・snow型(OW)の両方が"普通"の読み方なので、どちらか一致すればtrickyにしない
DUAL_EXPECT = {
    'ow': (['AW', 'OW'], 'アウ/オウ'),
}

# ere/ire/ureなどのr音化母音+eは単語ごとに音がバラバラで「これが正解」という基準がないため、
# 含まれていたら一律trickyとして扱う
ALWAYS_TRICKY_CLUSTERS = {
    'ere': 'ereは単語によって読み方がバラバラ(there/here/wereで違う音)だよ',
}

# 単純な文字/音素ルールだけでは判定しにくい超高頻度の不規則単語(いわゆる真の"サイトワード")
# 手作業で補った例外リスト。ここに載っているものは規則からの逸脱が明確なため tricky:true とする。
MANUAL_EXCEPTIONS = {
    'a':     ('a', 'aが弱い曖昧母音(schwa)で発音される'),
    'the':   ('e', 'eが弱い曖昧母音(schwa)で発音される'),
    'to':    ('o', 'oが長いu音(ウー)になる'),
    'do':    ('o', 'oが長いu音(ウー)になる'),
    'into':  ('o', '語末のoが長いu音(ウー)になる'),
    'two':   ('tw', 'twのwは発音しない黙字だよ(トゥーと読むよ)'),
    'who':   ('wh', 'whは本当はwの音のはずだけど、hの音(フー)で読むよ'),
    'are':   ('are', '母音字+eの規則(care型)に従わずcarと同じ音になる'),
    'water': ('a', 'aがオ音に近い発音になる'),
    'what':  ('a', 'aが短いa音ではなくu音に近い発音になる'),
    'many':  ('a', 'aが短いa音ではなくe音に近い発音になる'),
    'other': ('o', 'oが短いo音ではなくu音になる'),
    'words': ('or', 'orがr音化母音のer音になる'),
    'one':   (None, '綴りと発音が一致しない特殊語(ワン)'),
    'once':  (None, '綴りと発音が一致しない特殊語(ワンス)'),
}


def judge_word(word):
    """
    return (tricky: bool, highlight: str|None, note: str)
    完璧な精度は求めず、実用レベルの機械判定。
    """
    w = word.lower()

    # 0) 手作業の例外リスト(超高頻度の不規則語)
    if w in MANUAL_EXCEPTIONS:
        highlight, note = MANUAL_EXCEPTIONS[w]
        return (True, highlight, note)

    phones = get_phones(w)
    if phones is None:
        return (False, None, '')  # 発音データなし判定不能 -> 規則通り扱い(要目視確認)

    # 1) wr-, kn-, gn- 語頭の黙字
    if w.startswith('wr') and 'W' not in phones[:1]:
        return (True, 'wr', 'wrのwは発音しない黙字だよ。rの音だけで読むよ')
    if w.startswith('kn') and phones[0] != 'K':
        return (True, 'kn', 'knのkは発音しない黙字だよ。nの音だけで読むよ')
    if w.startswith('gn') and phones[0] != 'G':
        return (True, 'gn', 'gnのgは発音しない黙字だよ。nの音だけで読むよ')

    # 2) wh- が h音(HH)になる特殊ケース(who, whole, whose など)
    if w.startswith('wh') and phones and phones[0] == 'HH':
        return (True, 'wh', 'whは本当はwの音のはずだけど、ここではhの音(ホゥ)で読むよ')

    # 3) 語末mb, mn の黙字 (comb, autumn など)
    if w.endswith('mb') and phones and phones[-1] != 'B':
        return (True, 'mb', 'mbの最後のbは発音しない黙字だよ')
    if w.endswith('mn') and phones and phones[-1] != 'N':
        pass  # mn語末でnが脱落するケースは稀、今回は判定なし

    # 4) 母音+子音+e (magic e) パターン (r-controlled母音(are/ore/ire等)は別ルールなので除外)
    m = re.search(r'([aeiou])([bcdfghjklmnpqstvz])e$', w)
    if m:
        vowel, cons = m.group(1), m.group(2)
        expect_phone, expect_kana = MAGIC_E_EXPECT[vowel]
        if not has_phone(phones, expect_phone):
            return (True, vowel, '母音+子音+eのルールなら「'+expect_kana+'」と伸ばす音になるはずだけど、'
                    + 'この単語では違う音で読むよ')

    # 5) ere などバラバラな読みになるクラスタは一律tricky
    for cluster, note in ALWAYS_TRICKY_CLUSTERS.items():
        if cluster in w:
            return (True, cluster, note)

    # 6) ow など複数の読み方がどちらも"普通"なクラスタ(どちらか一致すればOK)
    for digraph, (expect_phones, expect_kana) in DUAL_EXPECT.items():
        if digraph in w:
            if not any(has_phone(phones, p) for p in expect_phones):
                return (True, digraph, digraph + 'は本当は「' + expect_kana
                        + '」と読むことが多いけど、この単語では違う音になるよ')

    # 7) 母音二重字(digraph)
    for digraph, (expect_phone, expect_kana) in DIGRAPH_EXPECT.items():
        idx = w.find(digraph)
        if idx != -1:
            if not has_phone(phones, expect_phone):
                return (True, digraph, digraph + 'は本当は「' + expect_kana
                        + '」と読むことが多いけど、この単語では違う音になるよ')

    # 8) 語末の単独s が z音になる(語幹がsで終わる短い基本語のみを対象、複数形の-sは対象外にする簡易ヒューリスティック)
    if w.endswith('s') and not w.endswith('ss') and len(w) <= 4:
        if phones and phones[-1] == 'Z':
            return (True, 's', '語の終わりのsは「ス」ではなく濁って「ズ」と読むよ')

    # 9) 語末の単独f が v音になる (of など)
    if w.endswith('f') and len(w) <= 3:
        if phones and phones[-1] == 'V':
            return (True, 'f', '語の終わりのfは「フ」ではなく濁って「ヴ」と読むよ')

    return (False, None, '')


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def main():
    fry_words = load_json(r"C:\Users\PC_USER\Documents\sight-words-app\fry_words.json")
    list1_ref = load_json(r"C:\Users\PC_USER\Desktop\list1_phonics.json")
    ref_by_word = {r['word'].lower(): r for r in list1_ref}

    # ---- Step 3: List1で機械判定 vs 人力判定を突き合わせ ----
    list1_words = [w for w in fry_words if w['list'] == 1]
    mismatches = []
    for w in list1_words:
        word = w['word']
        auto_tricky, auto_highlight, auto_note = judge_word(word)
        ref = ref_by_word.get(word.lower())
        if ref is None:
            mismatches.append((word, 'REF_MISSING', auto_tricky, None))
            continue
        if bool(ref['tricky']) != auto_tricky:
            mismatches.append((word, 'tricky', auto_tricky, ref['tricky']))

    print("=== Step3: List1 突き合わせ結果 ===")
    print("List1 語数:", len(list1_words), " 人力trueの数:", sum(1 for r in list1_ref if r['tricky']))
    print("食い違い件数:", len(mismatches))
    for word, kind, auto, ref in mismatches:
        print(f"  {word:12s} kind={kind:12s} machine={auto} reference={ref}")

    # ---- Step 4/5: 全1000語の機械判定を生成 ----
    all_results = []
    per_list_tricky = {}
    for w in fry_words:
        word = w['word']
        tricky, highlight, note = judge_word(word)
        all_results.append({
            "word": word,
            "tricky": tricky,
            "highlight": highlight,
            "note": note
        })
        per_list_tricky.setdefault(w['list'], [0, 0])
        per_list_tricky[w['list']][1] += 1
        if tricky:
            per_list_tricky[w['list']][0] += 1

    out_path = r"C:\Users\PC_USER\Documents\sight-words-app\fry_phonics.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print("\n=== Step5: List別 tricky率 ===")
    rates = []
    for listnum in sorted(per_list_tricky):
        tricky_n, total_n = per_list_tricky[listnum]
        rate = tricky_n / total_n * 100
        rates.append(rate)
        print(f"  List {listnum:2d}: {tricky_n:3d} / {total_n:3d} = {rate:5.1f}%")

    avg = sum(rates) / len(rates)
    print(f"\n平均tricky率: {avg:.1f}%")
    print("List1(人力)のtricky率:", sum(1 for r in list1_ref if r['tricky']), "/", len(list1_ref),
          "=", round(sum(1 for r in list1_ref if r['tricky']) / len(list1_ref) * 100, 1), "%")

    print("\n出力:", out_path, " 件数:", len(all_results))


if __name__ == '__main__':
    main()
