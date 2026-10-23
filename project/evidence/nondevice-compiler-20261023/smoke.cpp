#include <string>
#include <vector>
int main() { std::vector<std::string> v{"retained", "cross-compiler"}; return v.size() == 2 ? 0 : 1; }
