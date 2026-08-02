# 案件・成果物・レビュー基盤

## ER構造

```text
organizations 1--N projects 1--N project_members N--1 users
organizations 1--N projects 1--N artifacts 1--N artifact_versions
artifacts 0..1--1 current artifact_version
projects 1--N ai_runs
artifact_versions 1--N reviews 1--N review_comments
artifact_versions 1--N approval_events
```

`projects`、`artifacts`、`reviews`、`ai_runs`、`approval_events` は `organization_id` を持つ。APIはアクセストークン、`users.cognito_sub`、有効ユーザー、組織所属、所属ロール、リソースの組織IDの順に検証し、入力された `organization_id` だけを信用しない。案件ロールは `project_members.project_role`、組織RBACは `membership_roles` として分離する。

## 状態遷移

```text
draft -> ai_reviewing -> human_reviewing -> approved
human_reviewing -> revision_requested -> 新規artifact_version -> ai_reviewing
```

`submit`、AI合格確認、人間レビュー移行、承認、差し戻しはサービス層で検証する。`draft -> approved`、最新でない版の承認、未解決criticalコメントがある承認、基準未満AIレビューの合格、他組織ユーザーの操作を拒否する。AI合格閾値は呼び出し側から設定可能で、既定値は95。承認済み版を含む全版はDBトリガーでUPDATE/DELETEを拒否し、修正は必ず新しい版として追加する。

## DB制約とインデックス

UUID主キー、timezone付き日時、RESTRICT外部キーを基本とする。`(organization_id, project_code)`、`(project_id, user_id)`、`(artifact_id, version_number)` は一意。状態・種別・score 0〜100・非負料金/トークン関連値・レビュー主体の排他をCHECK制約で検証する。検索用に組織/状態、案件/状態、成果物/作成日時、版/レビュー状態等の複合インデックスを持つ。

循環参照を避けるため `artifacts.current_version_id` はnullableでテーブル作成後にFKを追加する。`approval_events` はUPDATE/DELETE、`artifact_versions` はUPDATE/DELETE、レビュー履歴はDELETEをトリガーで拒否する。DBだけでは組織を跨ぐ外部キー整合性や状態遷移を完全に表せないため、サービス層でも所属と組織IDを照合する。

## API

すべて `/api/v1` 配下で認証必須。

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `POST /projects/{project_id}/artifacts`
- `POST /artifacts/{artifact_id}/versions`
- `POST /artifact-versions/{version_id}/reviews`
- `POST /reviews/{review_id}/comments`
- `POST /artifact-versions/{version_id}/submit`
- `POST /artifact-versions/{version_id}/approve`
- `POST /artifact-versions/{version_id}/request-changes`

## Migrationとローカル検証

revision `57d2abd856ae` は `0002_identity_access` に続くadditive migrationで、8テーブル、FK、CHECK/UNIQUE、インデックス、履歴保護トリガーのみを追加する。既存テーブルやデータは削除・更新しない。

```bash
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@LOCAL_HOST/LOCAL_DB pytest -q
APP_DATABASE_URL=postgresql+psycopg://offline:offline@db.invalid/system_navigator alembic upgrade 0002_identity_access:head --sql
APP_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@LOCAL_HOST/LOCAL_DB alembic downgrade 0002_identity_access
APP_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@LOCAL_HOST/LOCAL_DB alembic upgrade head
```

RDS接続・本番migration・Terraform plan/apply/destroy・AWS変更・ECR push・ECS deployは禁止。実行前に対象DB、バックアップ、停止許容時間、ロック、ロールバック、既存データ量、拡張/権限、オフラインSQL差分をレビューする。

## セキュリティ

AI実行履歴にはAPIキー、トークン、完全なプロンプト、顧客秘密情報を保存しない。エラーはサニタイズし、ファイル本体はDBではなくstorage keyとcontent hashだけを保存する。外部AI APIへの通信はこの実装に含まれない。
