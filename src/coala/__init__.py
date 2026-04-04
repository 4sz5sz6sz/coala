import asyncio
from logging import getLogger
from pathlib import Path
import yaml
from infinitecraft import InfiniteCraft

log = getLogger(__name__)

# Global cache to minimize API calls and redundant checks across different labs
_ALREADY_CHECKED_RECIPES: set[str] = set()
_FUSION_CACHE: dict[tuple[str, str], str] = {}


class Lab:
    """A laboratory for fusing elements and verifying recipes using InfiniteCraft.

    This class provides tools to load element recipes from YAML files,
    fuse elements, and recursively verify that target elements can be created
    from their defined ingredients using InfiniteCraft's API.

    Attributes:
        lab_name (str): The name of the laboratory (e.g., 'tutorial_lab').
        cache_storage_path (str): File path for InfiniteCraft discovery storage.
        game (InfiniteCraft): The underlying InfiniteCraft game instance.
        recipes (dict[str, list[str]]): Loaded recipes mapping target names to ingredients.
        lab_path (Path): Directory path containing the lab's YAML configuration files.
    """

    def __init__(self, lab_name: str, cache_storage_path: str):
        """Initializes the Lab with a name and a storage path.

        Args:
            lab_name: The name of the lab, corresponding to a directory in coala.
            cache_storage_path: The file path where InfiniteCraft discovery data is stored.
        """
        self.lab_name = lab_name
        self.cache_storage_path = cache_storage_path
        self.game = InfiniteCraft(discoveries_storage=cache_storage_path)
        self.recipes: dict[str, list[str]] = {}
        # Locate the lab directory relative to the package location
        self.lab_path = Path(__file__).parent / lab_name

    async def start(self):
        """Starts the InfiniteCraft session and loads recipes from YAML files.

        This method initializes the game engine and populates the recipes dictionary
        by scanning the lab's directory for all YAML files.

        Raises:
            FileNotFoundError: If the lab directory does not exist.
            ValueError: If a recipe YAML is malformed or missing required keys.
        """
        if not self.lab_path.is_dir():
            raise FileNotFoundError(f"Lab directory not found: {self.lab_path}")

        await self.game.start()

        for file in self.lab_path.glob("*.yaml"):
            with open(file, "r", encoding="utf-8") as f:
                info = yaml.load(f, Loader=yaml.FullLoader)

            target = file.stem
            # Support both 'ingredients' and 'recipe' keys
            key = "ingredients" if "ingredients" in info else "recipe"

            if key not in info:
                raise ValueError(
                    f"YAML file '{file}' does not contain 'recipe' or 'ingredients'."
                )

            recipe = info[key]
            if not isinstance(recipe, list):
                raise ValueError(f"Recipe item '{key}' in '{file}' must be a list.")

            self.recipes[target] = recipe

    async def fuse(self, first_elem: str, second_elem: str) -> str:
        """Fuses two elements and returns the resulting element name.

        Args:
            first_elem: The name of the first element.
            second_elem: The name of the second element.

        Returns:
            The lowercase name of the resulting element.

        Raises:
            ValueError: If an element cannot be found in discoveries.
            RuntimeError: If the fusion fails or results in no name.
        """
        fusion_key: tuple[str, str] = tuple(
            sorted([first_elem.lower(), second_elem.lower()])
        )  # type: ignore (sorting only two elements)

        if fusion_key in _FUSION_CACHE:
            return _FUSION_CACHE[fusion_key]

        def get_element(name: str):
            items = self.game.get_discoveries()
            for item in items:
                if item.name and item.name.lower() == name.lower():
                    return item
            raise ValueError(f"Cannot find element of name: {name}")

        try:
            elem_0 = get_element(first_elem)
            elem_1 = get_element(second_elem)
        except ValueError as e:
            raise e

        # Verification using InfiniteCraft API
        result = await self.game.pair(elem_0, elem_1)

        # Throttling to approx 2 calls per second
        await asyncio.sleep(0.5)

        if result.name is None:
            raise RuntimeError(f"Fusion failed: {first_elem} + {second_elem}")

        result_name = result.name.lower()
        _FUSION_CACHE[fusion_key] = result_name
        return result_name

    async def assert_is_fusable(self, target: str | None = None):
        """Recursively asserts that a target (or all recipes) can be fused.

        This method verifies that every element in the lab has a valid recipe
        and that fusing the ingredients produces the expected target element.

        Args:
            target: Specific target element to verify. If None, all recipes are verified.

        Raises:
            AssertionError: If verification fails or a cycle is detected.
        """
        if target is None:
            for elem in list(self.recipes.keys()):
                await self._assert_fusable_recursive(elem, set())
        else:
            await self._assert_fusable_recursive(target, set())

    async def _assert_fusable_recursive(self, target: str, visited: set[str]):
        """Internal recursive helper to verify element fusability.

        Args:
            target: The element to verify.
            visited: Tracks elements in current recursion stack to detect cycles.
        """
        if target in _ALREADY_CHECKED_RECIPES:
            return

        if target in visited:
            raise AssertionError(
                f"Cycle detected in recipes. '{target}' was referenced twice."
            )

        visited.add(target)

        if target not in self.recipes:
            raise AssertionError(
                f"Referenced element '{target}' has no recipe defined."
            )

        ingredients = self.recipes[target]

        # Base elements have empty ingredients list
        if ingredients:
            if len(ingredients) != 2:
                raise AssertionError(
                    f"InfiniteCraft only supports pairing exactly 2 elements. '{target}' has {len(ingredients)}."
                )

            # Recursive check for ingredients
            for element in ingredients:
                await self._assert_fusable_recursive(element, visited)

            # Verify the fusion result
            try:
                result_name = await self.fuse(ingredients[0], ingredients[1])
            except (ValueError, RuntimeError) as e:
                raise AssertionError(f"Failed to fuse {ingredients} for {target}: {e}")

            if result_name != target.lower():
                raise AssertionError(
                    f"Recipe mismatch: {ingredients} -> '{result_name}', expected '{target}'."
                )

        _ALREADY_CHECKED_RECIPES.add(target)
        visited.remove(target)
