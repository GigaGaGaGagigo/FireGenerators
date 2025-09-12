from typing import Any

from supabase._sync.client import SyncClient


class ProfileService:
    """
    Pure Python class responsible for handling profile data communication with the database (Supabase).
    No dependency on any UI framework (e.g., Streamlit).
    """

    def __init__(self, supabase_client: SyncClient, user_id: str):
        """
        Injects required dependencies (supabase client, user ID) at service initialization.

        Args:
            supabase_client: Client object for communicating with Supabase.
            user_id: Unique ID of the user whose data will be updated.
        """
        if not supabase_client or not user_id:
            raise ValueError("Supabase client and user_id must be provided.")
        self.db = supabase_client
        self.user_id = user_id

    def update_category(self, category: str, data: Any) -> bool:
        """
        Updates the profile data for a specific category in the database.

        Args:
            category: The category to update (e.g., "investment_goal").
            data: The data to be saved.

        Returns:
            bool: Whether the update was successful.

        Raises:
            Exception: If an error occurs during the database operation.
        """
        try:
            result = (
                self.db.table("profiles")
                .update({category: data})
                .eq("id", self.user_id)
                .execute()
            )
            # if result.data is not empty, consider it successful
            return bool(result.data)
        except Exception as e:
            # instead of UI feedback, raise an error to be handled by the caller
            print(f"ERROR: Supabase update failed for category '{category}': {e}")
            raise

    def update_news_logs(self, data: Any) -> bool:
        """
        Updates the profile data for a specific category in the database.

        Args:
            category: The category to update (e.g., "investment_goal").
            data: The data to be saved.

        Returns:
            bool: Whether the update was successful.

        Raises:
            Exception: If an error occurs during the database operation.
        """
        try:
            result = (
                self.db.table("user_news_logs")
                .insert(
                    {
                        "user_id": self.user_id,
                        "summary": data.get("summary", ""),
                        "key_opportunities": data.get("key_opportunities", []),
                        "potential_risks": data.get("potential_risks", []),
                        "analyst_take": data.get("analyst_take", ""),
                        "links": data.get("links", []),
                    }
                )
                .execute()
            )
            # if result.data is not empty, consider it successful
            return bool(result.data)
        except Exception as e:
            # instead of UI feedback, raise an error to be handled by the caller
            print(f"ERROR: Supabase update failed for category : {e}")
            raise


class MockProfileService(ProfileService):
    """
    Mock ProfileService for testing.
    Instead of connecting to a real database, it records which method was called with what values.
    """

    def __init__(self):
        # super().__init__(None, None) -> for test
        self.updated_categories: list[dict[str, Any]] = []

    def update_category(self, category: str, data: Any) -> bool:
        print(f"[Mock] update_category called with: {category}, {data}")
        self.updated_categories.append({"category": category, "data": data})
        return True
