from supabase import create_client
from app.core.config import SUPABASE_URL, SUPABASE_API_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_API_KEY)