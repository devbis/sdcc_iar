#ifdef __SDCC_mcs51
unsigned int
callee_global(unsigned char a, unsigned int b)
{
  return a + b;
}

unsigned int
caller_global(unsigned char a, unsigned int b)
{
  return callee_global(a, b);
}
#endif
