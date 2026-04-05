import asyncio
from logging import getLogger
from pathlib import Path

import fire
import yaml
from infinitecraft import InfiniteCraft

log = getLogger(__name__)


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
        self._checked_recipes: set[str] = set()

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
            try:
                with open(file, "r", encoding="utf-8") as f:
                    info = yaml.load(f, Loader=yaml.FullLoader)

                if info is None:
                    continue

                target = file.stem
                # Support both 'ingredients' and 'recipe' keys
                key = "ingredients" if "ingredients" in info else "recipe"

                if key not in info:
                    raise ValueError(f"Missing 'ingredients' or 'recipe' key.")

                recipe = info[key]
                if not isinstance(recipe, list):
                    raise ValueError(f"Recipe item '{key}' in '{file}' must be a list.")

                self.recipes[target] = recipe
            except Exception as e:
                raise ValueError(
                    f"Failed to load recipe from '{file.name}': {e}"
                ) from e

    async def close(self):
        """Closes the InfiniteCraft session and releases resources."""
        await self.game.stop()

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

        def get_element(name: str):
            items = self.game.get_discoveries()
            for item in items:
                if item.name and item.name.lower() == name.lower():
                    return item
            raise ValueError(f"Cannot find element of name: {name}")

        elem_0 = get_element(first_elem)
        elem_1 = get_element(second_elem)

        # Verification using InfiniteCraft API
        result = await self.game.pair(elem_0, elem_1)

        # Throttling to approx 2 calls per second
        await asyncio.sleep(0.5)

        if result.name is None:
            raise RuntimeError(f"Fusion failed: {first_elem} + {second_elem}")

        result_name = result.name.lower()
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
        if target in self._checked_recipes:
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
        else:
            if target.lower() not in ("fire", "earth", "water", "wind"):
                raise ValueError("recipe does not exist for non primitive elements")

        self._checked_recipes.add(target)

        visited.remove(target)


class CLI:
    """CLI for managing coala labs."""

    def create_lab(self, lab_name: str):
        """Creates a new lab with basic elements and test structure.

        Args:
            lab_name: The name of the lab directory to create.
        """
        if not lab_name.endswith("_lab"):
            lab_name = lab_name + "_lab"
        # Create src directory and elements
        lab_dir = Path(__file__).parent / lab_name
        lab_dir.mkdir(exist_ok=True)
        elements = ["earth", "fire", "water", "wind"]
        for elem in elements:
            with open(lab_dir / f"{elem}.yaml", "w", encoding="utf-8") as f:
                f.write("ingredients: []\n")

        with open(lab_dir / f"__init__.py", "w") as f:
            ...

        # Create tests directory and test file
        project_root = Path(__file__).parent.parent.parent
        test_dir = project_root / "tests" / lab_name
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "__init__.py").touch()

        test_content = f"""from coala import Lab
import pytest


@pytest.fixture(scope="module")
def lab_name() -> str:
    return "{lab_name}"


async def test_lab_load(lab: Lab):
    \"\"\"assert lab fixture is loaded without any error\"\"\"
    assert isinstance(lab, Lab)
    assert lab.lab_name == "{lab_name}"


async def test_lab_integrity(lab: Lab):
    \"\"\"Verifies that all recipes in the lab are structurally sound and fusable.\"\"\"
    await lab.assert_is_fusable()


async def test_fuse_fire_and_water(lab: Lab):
    result = await lab.fuse("fire", "water")
    assert result == "steam"
"""
        with open(test_dir / "test_each_elems.py", "w", encoding="utf-8") as f:
            f.write(test_content)

        print(f"'{lab_name}' 연구소를 {lab_dir}에 생성했습니다.")
        print(f"'{lab_name}'을 위한 테스트 구조를 {test_dir}에 생성했습니다.")
        print("\n다음 단계:")
        print(
            f'1. 새 연구실 검증을 위해 테스트를 실행하세요: `uv run pytest -k "{lab_name}" -v`'
        )
        print(
            f"2. `src/coala/{lab_name}/`에 새로운 원소 레시피를 추가하세요 (예: ingredients가 [fire, water]인 steam.yaml)"
        )
        print(
            f"3. `tests/{lab_name}/test_each_elems.py`에 테스트를 더 추가하여 발견한 내용을 검증하세요"
        )


def cli():
    fire.Fire(CLI)
