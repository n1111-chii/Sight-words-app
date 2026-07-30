"""
短文セクション(list1〜10_sentences.json、199文)の音声をGemini TTS(声: Leda)で
事前生成するスクリプト。

単語単体の発音はLedaだと不自然になることが確認されたため、単語音声は生成しない
(単語は引き続きWeb Speech APIで再生する、ハイブリッド構成)。

使い方:
  python generate_audio.py --limit 3   # パイロット: 先頭3件だけ試す
  python generate_audio.py             # 本番: 対象全件を生成(既存ファイルはスキップ)

前提: .env に GEMINI_API_KEY を設定、ffmpeg がPATH上にあること。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

from dotenv import load_dotenv

load_dotenv()

MODEL = "gemini-2.5-flash-preview-tts"
VOICE = "Leda"
OUT_DIR = "audio"
MANIFEST_PATH = "audio-manifest.json"
FAILED_PATH = "audio_failed.json"
SLEEP_BETWEEN_CALLS = 6.5  # このモデルは1分10リクエストの上限が確認されたため余裕を持たせる
MAX_RETRIES = 5


def slugify(text):
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def collect_targets():
    """{ファイル名: 発話テキスト} の辞書を作る(短文199文のみ)。"""
    targets = {}
    for n in range(1, 11):
        path = "list{}_sentences.json".format(n)
        data = json.load(open(path, encoding="utf-8"))
        for item in data:
            fname = "sentence_list{}_{}.mp3".format(n, slugify(item["word"]))
            targets[fname] = item["sentence"]
    return targets


def generate_pcm(client, text):
    from google.genai import types

    # 命令文などをモデルが「指示」と誤解し、音声ではなくテキストで応答してしまう
    # ケースがあるため、読み上げ専用タスクであることを明示するプレフィックスを付ける。
    prompt = "Say in a natural, neutral tone: " + text

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
                )
            ),
        ),
    )
    part = response.candidates[0].content.parts[0]
    return part.inline_data.data


def pcm_to_mp3(pcm_bytes, out_path):
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "s16le", "-ar", "24000", "-ac", "1",
            "-i", "-",
            out_path,
        ],
        input=pcm_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "ignore")[-500:])


def write_manifest(targets):
    manifest = sorted(
        "audio/" + fname for fname in targets.keys()
        if os.path.exists(os.path.join(OUT_DIR, fname))
    )
    json.dump(manifest, open(MANIFEST_PATH, "w", encoding="utf-8"), ensure_ascii=False)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="先頭N件だけ処理する(パイロット用)")
    parser.add_argument("--manifest-only", action="store_true",
                         help="APIを呼ばず、既存の audio/ の内容から audio-manifest.json だけ再生成する")
    args = parser.parse_args()

    if args.manifest_only:
        targets = collect_targets()
        manifest = write_manifest(targets)
        print("manifest更新: {} / {} 件".format(len(manifest), len(targets)))
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY が .env に見つかりません", file=sys.stderr)
        sys.exit(1)

    from google import genai
    client = genai.Client(api_key=api_key)

    os.makedirs(OUT_DIR, exist_ok=True)
    targets = collect_targets()
    items = list(targets.items())
    if args.limit:
        items = items[: args.limit]

    total = len(items)
    done = 0
    failed = []
    t_start = time.time()

    for fname, text in items:
        out_path = os.path.join(OUT_DIR, fname)
        done += 1
        if os.path.exists(out_path):
            continue

        ok = False
        for attempt in range(MAX_RETRIES):
            try:
                pcm = generate_pcm(client, text)
                pcm_to_mp3(pcm, out_path)
                ok = True
                break
            except Exception as e:
                msg = str(e)
                if "RESOURCE_EXHAUSTED" in msg:
                    wait = 65  # レート制限は数十秒単位で解除されるため長めに待つ
                else:
                    wait = 2 ** attempt
                print("retry {} (attempt {}): {}".format(fname, attempt + 1, e), file=sys.stderr)
                time.sleep(wait)
        if not ok:
            failed.append(fname)

        if done % 20 == 0 or done == total:
            elapsed = time.time() - t_start
            print("{}/{} done, {} failed, {:.1f}s elapsed".format(done, total, len(failed), elapsed))

        time.sleep(SLEEP_BETWEEN_CALLS)

    write_manifest(targets)

    if failed:
        json.dump(failed, open(FAILED_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("完了: {}/{} 件処理, 失敗 {} 件".format(done, total, len(failed)))


if __name__ == "__main__":
    main()
