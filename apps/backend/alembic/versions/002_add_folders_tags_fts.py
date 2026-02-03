"""Add folders, tags, and FTS indexes

Revision ID: 002_add_folders_tags_fts
Revises: 001_initial
Create Date: 2025-02-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR


# revision identifiers
revision = '002_add_folders_tags_fts'
down_revision = None  # Set to your previous migration ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============================================
    # Create folders table
    # ============================================
    op.create_table(
        'folders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('parent_id', sa.String(36), sa.ForeignKey('folders.id'), nullable=True),
        sa.Column('path', sa.String(1000), nullable=False, server_default='/'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_folders_path', 'folders', ['path'])
    
    # ============================================
    # Create tags table
    # ============================================
    op.create_table(
        'tags',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('color', sa.String(7), server_default='#6366f1'),
        sa.Column('is_system', sa.Boolean, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_tags_name', 'tags', ['name'])
    
    # ============================================
    # Create meeting_tags association table
    # ============================================
    op.create_table(
        'meeting_tags',
        sa.Column('meeting_id', sa.String(36), sa.ForeignKey('meetings.id'), primary_key=True),
        sa.Column('tag_id', sa.String(36), sa.ForeignKey('tags.id'), primary_key=True),
    )
    
    # ============================================
    # Add folder_id column to meetings
    # ============================================
    op.add_column('meetings', sa.Column('folder_id', sa.String(36), sa.ForeignKey('folders.id'), nullable=True))
    
    # ============================================
    # Add TSVECTOR columns for Full Text Search
    # ============================================
    op.add_column('meetings', sa.Column('search_vector', TSVECTOR, nullable=True))
    op.add_column('transcript_segments', sa.Column('search_vector', TSVECTOR, nullable=True))
    
    # Create GIN indexes for FTS
    op.create_index('idx_meeting_search_vector', 'meetings', ['search_vector'], postgresql_using='gin')
    op.create_index('idx_segment_search_vector', 'transcript_segments', ['search_vector'], postgresql_using='gin')
    
    # ============================================
    # Create FTS trigger function
    # ============================================
    op.execute("""
        CREATE OR REPLACE FUNCTION meetings_search_vector_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := 
                setweight(to_tsvector('simple', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('simple', COALESCE(NEW.transcript_raw, '')), 'B') ||
                setweight(to_tsvector('simple', COALESCE(NEW.summary_json, '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER meetings_search_update
        BEFORE INSERT OR UPDATE ON meetings
        FOR EACH ROW EXECUTE FUNCTION meetings_search_vector_trigger();
    """)
    
    op.execute("""
        CREATE OR REPLACE FUNCTION segments_search_vector_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := 
                to_tsvector('simple', COALESCE(NEW.content_raw, '')) ||
                to_tsvector('simple', COALESCE(NEW.content_polished, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER segments_search_update
        BEFORE INSERT OR UPDATE ON transcript_segments
        FOR EACH ROW EXECUTE FUNCTION segments_search_vector_trigger();
    """)
    
    # ============================================
    # Insert default system tags
    # ============================================
    op.execute("""
        INSERT INTO tags (id, name, color, is_system) VALUES 
        (gen_random_uuid()::text, '重要', '#ef4444', true),
        (gen_random_uuid()::text, '待追蹤', '#f59e0b', true),
        (gen_random_uuid()::text, '已完成', '#22c55e', true),
        (gen_random_uuid()::text, '待審核', '#6366f1', true),
        (gen_random_uuid()::text, '內部會議', '#8b5cf6', true),
        (gen_random_uuid()::text, '外部會議', '#06b6d4', true);
    """)


def downgrade() -> None:
    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS meetings_search_update ON meetings;")
    op.execute("DROP TRIGGER IF EXISTS segments_search_update ON transcript_segments;")
    op.execute("DROP FUNCTION IF EXISTS meetings_search_vector_trigger();")
    op.execute("DROP FUNCTION IF EXISTS segments_search_vector_trigger();")
    
    # Drop indexes
    op.drop_index('idx_meeting_search_vector', table_name='meetings')
    op.drop_index('idx_segment_search_vector', table_name='transcript_segments')
    
    # Drop columns
    op.drop_column('meetings', 'search_vector')
    op.drop_column('transcript_segments', 'search_vector')
    op.drop_column('meetings', 'folder_id')
    
    # Drop tables
    op.drop_table('meeting_tags')
    op.drop_table('tags')
    op.drop_table('folders')
