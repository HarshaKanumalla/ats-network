# backend/app/core/database/query_optimizer.py

from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import logging
import json
from bson import ObjectId

from ...core.exceptions import QueryOptimizationError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class QueryOptimizer:
    """Manages query optimization and performance enhancement for database operations."""

    def __init__(self):
        """Initialize query optimizer with configuration settings."""
        # Query analysis thresholds
        self.slow_query_threshold = 1000  # milliseconds
        self.complex_query_threshold = 5  # number of conditions
        self.large_result_threshold = 1000  # documents

        # Index optimization settings
        self.index_usage_threshold = 0.8  # 80% index utilization target
        self.compound_index_limit = 4  # maximum fields in compound index

        # Query patterns storage
        self.query_patterns = {}
        self.pattern_threshold = 10  # minimum occurrences to identify pattern

        logger.info("Query optimizer initialized with performance settings")

    def optimize_find_query(
        self,
        query: Dict[str, Any],
        collection: str
    ) -> Dict[str, Any]:
        """Optimize find query based on collection-specific rules."""
        try:
            if not isinstance(query, dict):
                raise QueryOptimizationError("Invalid query format. Expected a dictionary.")
            if not isinstance(collection, str) or not collection:
                raise QueryOptimizationError("Invalid collection name.")

            optimized = query.copy()

            # Add commonly used fields to projection
            if collection == "users":
                optimized.setdefault("projection", {
                    "passwordHash": 0,
                    "resetToken": 0,
                    "verificationToken": 0,
                    "loginAttempts": 0
                })
            elif collection == "testSessions":
                optimized.setdefault("projection", {
                    "rawData": 0,
                    "debugLogs": 0
                })

            # Add index hints based on known indexes
            if collection == "testSessions" and "vehicleId" in query:
                optimized["hint"] = [("vehicleId", 1), ("testDate", -1)]
            elif collection == "centers" and "location" in query:
                optimized["hint"] = "location_2dsphere"

            # Add query modifiers for better performance
            if "sort" in optimized and "skip" in optimized:
                # Use limit to reduce memory usage with skip
                optimized.setdefault("limit", 1000)

            logger.info(f"Optimized query for collection '{collection}': {optimized}")
            return optimized

        except Exception as e:
            logger.error(f"Query optimization error for collection '{collection}': {str(e)}")
            raise QueryOptimizationError(f"Failed to optimize query: {str(e)}")

    def optimize_aggregation_pipeline(
        self,
        pipeline: List[Dict[str, Any]],
        collection: str
    ) -> List[Dict[str, Any]]:
        """Optimize aggregation pipeline for better performance."""
        try:
            if not isinstance(pipeline, list):
                raise QueryOptimizationError("Invalid pipeline format. Expected a list of stages.")
            if not isinstance(collection, str) or not collection:
                raise QueryOptimizationError("Invalid collection name.")

            optimized = []

            # Move $match stages as early as possible
            match_stages = []
            other_stages = []

            for stage in pipeline:
                if "$match" in stage:
                    match_stages.append(stage)
                else:
                    other_stages.append(stage)

            optimized.extend(match_stages)
            optimized.extend(other_stages)

            # Add index hints where applicable
            if collection == "centers":
                optimized.append({"$hint": {"location.coordinates": "2dsphere"}})

            # Optimize $lookup and $unwind stages
            for stage in optimized:
                if "$lookup" in stage:
                    stage["$lookup"]["allowDiskUse"] = True
                if "$unwind" in stage:
                    stage["$unwind"]["preserveNullAndEmptyArrays"] = True

            # Add memory usage optimizations
            if any("$group" in stage for stage in pipeline):
                optimized.append({"$allowDiskUse": True})

            logger.info(f"Optimized aggregation pipeline for collection '{collection}': {optimized}")
            return optimized

        except Exception as e:
            logger.error(f"Pipeline optimization error for collection '{collection}': {str(e)}")
            raise QueryOptimizationError(f"Failed to optimize pipeline: {str(e)}")

    def create_date_range_query(
        self,
        start_date: datetime,
        end_date: datetime,
        date_field: str = "createdAt"
    ) -> Dict[str, Any]:
        """Create optimized date range query."""
        try:
            if not isinstance(start_date, datetime) or not isinstance(end_date, datetime):
                raise QueryOptimizationError("Invalid date format. Expected datetime objects.")

            return {
                date_field: {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }
        except Exception as e:
            logger.error(f"Date range query creation error: {str(e)}")
            raise QueryOptimizationError("Failed to create date range query")

    def create_pagination_options(
        self,
        page: int,
        per_page: int,
        sort_field: str = "createdAt",
        sort_order: int = -1
    ) -> Dict[str, Any]:
        """Create optimized pagination options."""
        try:
            if page < 1 or per_page < 1:
                raise QueryOptimizationError("Page and per_page must be greater than 0.")

            options = {
                "skip": (page - 1) * per_page,
                "limit": per_page,
                "sort": [(sort_field, sort_order)]
            }

            # Add index hint if available
            if sort_field in ["createdAt", "updatedAt"]:
                options["hint"] = [(sort_field, sort_order)]

            logger.info(f"Created pagination options: {options}")
            return options

        except Exception as e:
            logger.error(f"Pagination options creation error: {str(e)}")
            raise QueryOptimizationError("Failed to create pagination options")

    def create_geospatial_query(
        self,
        longitude: float,
        latitude: float,
        max_distance: int = 5000
    ) -> Dict[str, Any]:
        """Create optimized geospatial query."""
        try:
            if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
                raise QueryOptimizationError("Invalid longitude or latitude values.")

            return {
                "location.coordinates": {
                    "$near": {
                        "$geometry": {
                            "type": "Point",
                            "coordinates": [longitude, latitude]
                        },
                        "$maxDistance": max_distance
                    }
                }
            }
        except Exception as e:
            logger.error(f"Geospatial query creation error: {str(e)}")
            raise QueryOptimizationError("Failed to create geospatial query")

    def analyze_query_performance(
        self,
        query: Dict[str, Any],
        collection: str,
        execution_time: float
    ) -> Dict[str, Any]:
        """Analyze query performance and suggest optimizations."""
        try:
            if not isinstance(query, dict):
                raise QueryOptimizationError("Invalid query format. Expected a dictionary.")
            if not isinstance(collection, str) or not collection:
                raise QueryOptimizationError("Invalid collection name.")

            analysis = {
                "performance": {
                    "execution_time": execution_time,
                    "is_slow": execution_time > self.slow_query_threshold
                },
                "complexity": self._analyze_query_complexity(query),
                "suggestions": []
            }

            # Add query pattern to storage
            query_hash = self._hash_query(query)
            self.query_patterns[query_hash] = self.query_patterns.get(query_hash, 0) + 1

            # Generate optimization suggestions
            if analysis["performance"]["is_slow"]:
                analysis["suggestions"].extend(
                    self._generate_performance_suggestions(query, collection)
                )

            if analysis["complexity"]["is_complex"]:
                analysis["suggestions"].extend(
                    self._generate_complexity_suggestions(query)
                )

            logger.info(f"Query performance analysis: {analysis}")
            return analysis

        except Exception as e:
            logger.error(f"Query analysis error for collection '{collection}': {str(e)}")
            raise QueryOptimizationError("Failed to analyze query performance")

    def _analyze_query_complexity(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze query complexity and structure."""
        condition_count = self._count_conditions(query)
        has_or = "$or" in query
        has_in = any(isinstance(v, list) for v in query.values())

        return {
            "condition_count": condition_count,
            "has_or_conditions": has_or,
            "has_in_conditions": has_in,
            "is_complex": (
                condition_count > self.complex_query_threshold or
                has_or or
                has_in
            )
        }

    def _generate_performance_suggestions(
        self,
        query: Dict[str, Any],
        collection: str
    ) -> List[str]:
        """Generate performance optimization suggestions."""
        suggestions = []

        # Check for missing indexes
        indexed_fields = self._get_collection_indexes(collection)
        query_fields = set(query.keys())
        missing_indexes = query_fields - indexed_fields

        if missing_indexes:
            suggestions.append(
                f"Consider adding indexes for fields: {', '.join(missing_indexes)}"
            )

        # Suggest query structure improvements
        if "$or" in query:
            suggestions.append(
                "Consider restructuring OR conditions or adding compound indexes"
            )

        return suggestions

    def _count_conditions(self, query: Dict[str, Any], depth: int = 0) -> int:
        """Count query conditions recursively."""
        count = 0

        if depth > 5:  # Prevent excessive recursion
            return count

        for key, value in query.items():
            if key.startswith("$"):
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            count += self._count_conditions(item, depth + 1)
            elif isinstance(value, dict):
                count += self._count_conditions(value, depth + 1)
            else:
                count += 1

        return count

    def _hash_query(self, query: Dict[str, Any]) -> str:
        """Create hash of query structure for pattern matching."""
        # Remove specific values but keep structure
        structure = self._get_query_structure(query)
        return hash(json.dumps(structure, sort_keys=True))

    def _get_query_structure(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Extract query structure without specific values."""
        structure = {}

        for key, value in query.items():
            if isinstance(value, dict):
                structure[key] = self._get_query_structure(value)
            elif isinstance(value, list):
                structure[key] = "array"
            else:
                structure[key] = "value"

        return structure

    def _get_collection_indexes(self, collection: str) -> Set[str]:
        """Get indexed fields for collection."""
        # This would typically come from database metadata
        # Hardcoded for example
        common_indexes = {
            "users": {"_id", "email", "role", "createdAt"},
            "centers": {"_id", "centerCode", "location.coordinates"},
            "testSessions": {"_id", "vehicleId", "centerId", "testDate"},
            "vehicles": {"_id", "registrationNumber"}
        }

        return common_indexes.get(collection, set())


# Initialize query optimizer
query_optimizer = QueryOptimizer()