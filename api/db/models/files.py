"""File-manager tables (reference columns; docs list the entities, and `file.parent_id` index)."""
from __future__ import annotations

import peewee

from api.db.models.base import BaseModel


class File(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    parent_id = peewee.CharField(max_length=32, null=False, help_text="parent folder id", index=True)
    tenant_id = peewee.CharField(max_length=32, null=False, help_text="tenant id", index=True)
    created_by = peewee.CharField(max_length=32, null=False, help_text="who created it", index=True)
    name = peewee.CharField(max_length=255, null=False, help_text="file name or folder name", index=True)
    location = peewee.CharField(max_length=255, null=True, help_text="where dose it store", index=True)
    size = peewee.BigIntegerField(default=0, index=True)
    type = peewee.CharField(max_length=32, null=False, help_text="file extension", index=True)
    source_type = peewee.CharField(max_length=128, null=False, default="", help_text="where dose this document come from", index=True)

    class Meta:
        table_name = "file"


class File2Document(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    file_id = peewee.CharField(max_length=32, null=True, help_text="file id", index=True)
    document_id = peewee.CharField(max_length=32, null=True, help_text="document id", index=True)

    class Meta:
        table_name = "file2document"


class FileCommit(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    folder_id = peewee.CharField(max_length=32, null=False, help_text="workspace folder id", index=True)
    parent_id = peewee.CharField(max_length=32, null=True, help_text="parent commit id", index=True)
    message = peewee.CharField(max_length=512, default="", help_text="commit message")
    author_id = peewee.CharField(max_length=32, null=False, help_text="user who created the commit", index=True)
    file_count = peewee.IntegerField(default=0, help_text="number of files in this commit")
    tree_state = peewee.TextField(null=True, help_text="JSON snapshot of the full folder tree at this commit")
    title = peewee.CharField(max_length=255, null=True, help_text="commit title (artifact-page edits)")
    comments = peewee.TextField(null=True, help_text="commit body/description (artifact-page edits)")

    class Meta:
        table_name = "file_commit"


class FileCommitItem(BaseModel):
    id = peewee.CharField(max_length=32, primary_key=True)
    commit_id = peewee.CharField(max_length=32, null=False, help_text="commit id", index=True)
    file_id = peewee.CharField(max_length=32, null=False, help_text="file id", index=True)
    operation = peewee.CharField(max_length=16, null=False, help_text="add / modify / delete / rename", index=True)
    old_hash = peewee.CharField(max_length=64, null=True, help_text="old content hash", index=True)
    new_hash = peewee.CharField(max_length=64, null=True, help_text="new content hash", index=True)
    old_location = peewee.CharField(max_length=255, null=True, help_text="old storage location")
    new_location = peewee.CharField(max_length=255, null=True, help_text="new storage location")
    old_name = peewee.CharField(max_length=255, null=True, help_text="old file name (for rename)")
    new_name = peewee.CharField(max_length=255, null=True, help_text="new file name (for rename)")
    diff = peewee.TextField(null=True, help_text="pre-computed unified diff (artifact-page edits)")
    content_after_storage = peewee.CharField(max_length=16, null=True, help_text="'minio' | 'es' - where the post-save blob lives", index=True)
    content_after_location = peewee.CharField(max_length=512, null=True, help_text="storage key/id for the post-save blob")
    slug_kwd = peewee.CharField(max_length=512, null=True, help_text="artifact page slug (<page_type>/<name>)", index=True)
    page_type_kwd = peewee.CharField(max_length=32, null=True, help_text="artifact page type", index=True)

    class Meta:
        table_name = "file_commit_item"
        indexes = ((("commit_id", "file_id"), True),)
