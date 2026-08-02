# クラウドA確認事項

- AWSアカウントIDが正しい
- root MFAとIAM Identity Center設定済み
- state S3が暗号化・Versioning・非公開
- DynamoDB lock有効
- RDSはPrivate、Multi-AZ、削除保護、最終スナップショット有効
- ECSはPrivate Subnet
- S3成果物バケットは非公開
- GitHub OIDCのリポジトリ条件が限定されている
- planに削除対象がない
- 月額見積もりを確認済み
- 初回apply後にALB、RDS、S3、ログを動作確認
