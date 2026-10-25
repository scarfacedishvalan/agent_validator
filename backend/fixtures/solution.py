class Solution:
    def longestConsecutive(self, nums) -> int:
        if not nums:
            return 0
        sorted_nums = sorted(nums)
        dedplicated = sorted(list(set(sorted_nums)))
        print(dedplicated)
        counter=1

        full_list = [1]
        for i, val in enumerate(dedplicated[:-1]):
            print(f"Comparing {dedplicated[i+1]} and {dedplicated[i]}")
            if dedplicated[i+1] - dedplicated[i] == 1:
                print("here")
                counter = counter + 1
                full_list.append(counter)
            else:
                counter = 1
        return max(full_list)

if __name__ == "__main__":
    sol = Solution()
    print(sol.longestConsecutive([0, -1]))