import yaml
from pathlib import Path
from logging import getLogger
import fire
import base64
import pickle

log = getLogger(__name__)


class Transmuter:
    """A simplified Transmuter using a local ground truth file."""

    def __init__(self):
        self.recipes = {}
        self.base_elements = set()
        dat_path = Path(__file__).parent / "combinations.dat"
        self._load(dat_path)

    def _load(self, path: Path):
        """Loads base elements and recipes from the packed dat file."""
        if not path.exists():
            log.warning(f"Data file not found: {path}")
            return

        with open(path, "rb") as f:
            encoded_data = f.read()

        raw_data = base64.b64decode(encoded_data)
        data = pickle.loads(raw_data)

        items = data["items"]
        recipes = data["recipes"]

        self.items = items
        # Map (idx_a, idx_b) -> idx_result
        self.recipe_map = {}
        for idx_a, idx_b, idx_res in recipes:
            key = tuple(sorted([idx_a, idx_b]))
            self.recipe_map[key] = idx_res

        self.base_elements = {items[0], items[1], items[2], items[3]}

        # Map name -> idx for faster lookup
        self.item_to_idx = {name.lower(): i for i, name in enumerate(items)}

    def fuse(self, a: str, b: str) -> str:
        """Fuses two elements and returns the resulting element name synchronously."""
        idx_a = self.item_to_idx.get(a.lower())
        idx_b = self.item_to_idx.get(b.lower())

        if idx_a is None or idx_b is None:
            raise RuntimeError(f"Element not found: {a if idx_a is None else b}")

        key = tuple(sorted([idx_a, idx_b]))
        idx_res = self.recipe_map.get(key)

        if idx_res is None:
            raise RuntimeError(f"Fusion failed: {a} + {b}")

        return self.items[idx_res].lower()


class Lab:
    """A laboratory for fusing elements and verifying recipes using local Transmuter.

    This class provides tools to load element recipes from YAML files,
    fuse elements, and recursively verify that target elements can be created
    from their defined ingredients.
    """

    def __init__(self, lab_name: str):
        """Initializes the Lab with a name and loads recipes.

        Args:
            lab_name: The name of the lab, corresponding to a directory in coala.
        """
        self.lab_name = lab_name
        self.transmuter = Transmuter()
        self.recipes: dict[str, list[str]] = {}
        # Locate the lab directory relative to the package location
        self.lab_path = Path(__file__).parent / lab_name
        self._load_recipes()

    def _load_recipes(self):
        """Loads recipes from YAML files in the lab directory."""
        if not self.lab_path.is_dir():
            # If lab_path is not a directory, we might be in a state where it's not yet created
            return

        for file in self.lab_path.glob("*.yaml"):
            with open(file, "r", encoding="utf-8") as f:
                info = yaml.load(f, Loader=yaml.FullLoader)

            if info is None:
                continue

            target = file.stem
            # Support both 'ingredients' and 'recipe' keys
            key = "ingredients" if "ingredients" in info else "recipe"

            if key not in info:
                # Some files might be base elements with ingredients: []
                if "ingredients" not in info and "recipe" not in info:
                    continue
                raise ValueError(f"Missing 'ingredients' or 'recipe' key in {file}.")

            recipe = info[key]
            if not isinstance(recipe, list):
                raise ValueError(f"Recipe item '{key}' in '{file}' must be a list.")

            self.recipes[target] = recipe

    def fuse(self, first_elem: str, second_elem: str) -> str:
        """Fuses two elements and returns the resulting element name.

        Args:
            first_elem: The name of the first element.
            second_elem: The name of the second element.

        Returns:
            The lowercase name of the resulting element.
        """
        return self.transmuter.fuse(first_elem, second_elem)

    def assert_is_fusable(self, target: str | None = None):
        """Recursively asserts that a target (or all recipes) can be fused.

        Args:
            target: Specific target element to verify. If None, all recipes are verified.
        """
        self._checked_recipes = set()
        if target is None:
            for elem in list(self.recipes.keys()):
                self._assert_fusable_recursive(elem, set())
        else:
            self._assert_fusable_recursive(target, set())

    def _assert_fusable_recursive(self, target: str, visited: set[str]):
        """Internal recursive helper to verify element fusability."""
        if hasattr(self, "_checked_recipes") and target in self._checked_recipes:
            return

        if target in visited:
            raise AssertionError(
                f"Cycle detected in recipes. '{target}' was referenced twice."
            )

        visited.add(target)

        # Base elements have empty ingredients list or match game base elements
        target_lower = target.lower()
        is_base_in_game = target_lower in self.transmuter.base_elements

        if target not in self.recipes:
            if is_base_in_game:
                if not hasattr(self, "_checked_recipes"):
                    self._checked_recipes = set()
                self._checked_recipes.add(target)
                visited.remove(target)
                return
            raise AssertionError(
                f"Referenced element '{target}' has no recipe defined."
            )

        ingredients = self.recipes[target]

        if ingredients:
            if len(ingredients) != 2:
                raise AssertionError(
                    f"Transmuter only supports pairing exactly 2 elements. '{target}' has {len(ingredients)}."
                )

            # Recursive check for ingredients
            for element in ingredients:
                self._assert_fusable_recursive(element, visited)

            # Verify the fusion result
            try:
                result_name = self.fuse(ingredients[0], ingredients[1])
            except RuntimeError as e:
                raise AssertionError(f"Failed to fuse {ingredients} for {target}: {e}")

            if result_name != target_lower:
                raise AssertionError(
                    f"Recipe mismatch: {ingredients} -> '{result_name}', expected '{target}'."
                )
        else:
            if not is_base_in_game:
                raise AssertionError(
                    f"Element '{target}' has no ingredients and is not a base element."
                )

        if not hasattr(self, "_checked_recipes"):
            self._checked_recipes = set()
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

        with open(lab_dir / "__init__.py", "w") as f:
            pass

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


def test_lab_load(lab: Lab):
    \"\"\"assert lab fixture is loaded without any error\"\"\"
    assert isinstance(lab, Lab)
    assert lab.lab_name == "{lab_name}"


def test_lab_integrity(lab: Lab):
    \"\"\"Verifies that all recipes in the lab are structurally sound and fusable.\"\"\"
    lab.assert_is_fusable()


def test_fuse_fire_and_water(lab: Lab):
    result = lab.fuse("fire", "water")
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
