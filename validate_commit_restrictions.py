from pathlib import Path
import sys

import re

# Define a regex pattern to match lab and element names ending with '.yaml'
pattern = r"\w+/(\w+_lab)/([\w+\s]+).yaml"

if __name__ == "__main__":
    elem_list = sys.argv[1:]

    ### 각 커밋은 원소 yaml 을 한 개 이하로 포함해야함
    if len(elem_list) <= 1:
        exit(0)

    parsed = [re.findall(pattern, elem) for elem in elem_list]

    parsed_by_lab = {}
    for regex_result in parsed:
        if not regex_result:
            continue
        lab, elem = regex_result[0]
        parsed_by_lab.setdefault(lab, []).append(elem)

    ###### 변경 목록에 모든 lab 에 해당하는 원소가 있다면 문제 없는 경우로 인지 (eg: pre-commit run -a)
    for lab, elems in parsed_by_lab.items():
        num_elems_in_lab = len(list((Path("./src/coala") / lab).glob("*.yaml")))
        if num_elems_in_lab != len(elems) and len(elems) > 1:
            items = "\n".join(sys.argv)
            print(
                f"각 커밋은 원소를 1개만 포함해야합니다. 포함된 원소 목록: \n {items}"
            )
            exit(1)
