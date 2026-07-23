# AGENTS.md

## Purpose

このリポジトリでは、コードレビュー指摘をRedmineへ照合・反映するCodexスキルを配布する。

## Required Skill

コードレビュー結果をRedmineへ反映する場合は、`$manage-redmine-review-findings`を使用する。

スキルがCodexへインストールされていない開発環境では、以下を読み、同じ手順に従う。

- `skills/manage-redmine-review-findings/SKILL.md`

レビュー観点とレビュー範囲は、リポジトリ内へ固定せず、その時点のユーザー指示に従う。

処理規則、Redmine設定、ステータス別の扱いはスキル側を正本とし、このファイルへ重複して記載しない。

## Development

スキルを変更した場合は、以下を実施する。

1. スクリプトの構文とCLIを確認する
2. `skill-creator`の`quick_validate.py`でスキル構造を検証する
3. APIキーや実環境の接続情報がリポジトリへ含まれていないことを確認する
