import 'package:flutter/material.dart';

import '../components/Header.dart';

class MyHomePage extends StatefulWidget {
  const MyHomePage({super.key});

  @override
  State<MyHomePage> createState() => _MyHomePageState();
}

class _MyHomePageState extends State<MyHomePage> {
  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body : Header(),
    );
    // This trailing comma makes auto-formatting nicer for build methods.
  }
}
