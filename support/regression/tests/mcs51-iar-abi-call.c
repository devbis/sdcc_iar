#ifdef __SDCC_mcs51
unsigned int
callee_u16(unsigned char a, unsigned int b) __iar
{
  return a + b;
}

unsigned int
caller_u16(unsigned char a, unsigned int b)
{
  return callee_u16(a, b);
}
#endif
