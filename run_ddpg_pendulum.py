import tensorflow as tf
import tensorflow.contrib.slim as slim
import numpy as np
import gym
import tflearn

from collections import deque
from policy_gradient.ddpg import Actor, Critic, OrnsteinUhlenbeckActionNoise

env = gym.make('Pendulum-v0')

sess = tf.Session()
actor_optimizer = tf.train.AdamOptimizer(learning_rate=0.0001)
critic_optimizer = tf.train.AdamOptimizer(learning_rate=0.001)

observation_shape = env.observation_space.shape[0]
action_shape = env.action_space.shape[0]

ACTION_BOUNDS = [2.0]
BATCH_SIZE = 64

def actor_network(states):
  net = slim.stack(states, slim.fully_connected, [24, 24], activation_fn=tf.nn.relu, scope='stack')
  net = slim.fully_connected(net, action_shape, activation_fn=tf.nn.tanh, scope='full')
  # mult with action bounds
  net = ACTION_BOUNDS * net
  return net

def critic_network(states, actions):
  state_net = slim.stack(states, slim.fully_connected, [5], activation_fn=tf.nn.relu, scope='stack_state')
  action_net = slim.stack(actions, slim.fully_connected, [5], activation_fn=tf.nn.relu, scope='stack_action')
  net = tf.concat([state_net, action_net], 1)
  net = slim.stack(net, slim.fully_connected, [5], activation_fn=tf.nn.relu, scope='stack')
  net = slim.fully_connected(net, 1, activation_fn=tf.nn.relu, scope='full')
  net = tf.squeeze(net, [1])
  return net

def actor_network_tflearn(states):
  with tf.variable_scope('actor'):
    net = tflearn.fully_connected(states, 400)
    # net = tflearn.layers.normalization.batch_normalization(net)
    net = tflearn.activations.relu(net)
    net = tflearn.fully_connected(net, 300)
    # net = tflearn.layers.normalization.batch_normalization(net)
    net = tflearn.activations.relu(net)
    # Final layer weights are init to Uniform[-3e-3, 3e-3]
    w_init = tflearn.initializations.uniform(minval=-0.003, maxval=0.003)
    out = tflearn.fully_connected(
        net, action_shape, activation='tanh', weights_init=w_init)
    # Scale output to -action_bound to action_bound
    scaled_out = tf.multiply(out, env.action_space.high)
    return scaled_out

def critic_network_tflearn(states, actions):
  with tf.variable_scope('critic'):
    net = tflearn.fully_connected(states, 400)
    # net = tflearn.layers.normalization.batch_normalization(net)
    net = tflearn.activations.relu(net)

    # Add the action tensor in the 2nd hidden layer
    # Use two temp layers to get the corresponding weights and biases
    t1 = tflearn.fully_connected(net, 300)
    t2 = tflearn.fully_connected(actions, 300)

    net = tflearn.activation(
        tf.matmul(net, t1.W) + tf.matmul(actions, t2.W) + t2.b, activation='relu')

    # linear layer connected to 1 output representing Q(s,a)
    # Weights are init to Uniform[-3e-3, 3e-3]
    # w_init = tflearn.initializations.uniform(minval=-0.003, maxval=0.003)
    # out = tflearn.fully_connected(net, 1, weights_init=w_init)
    out = tflearn.fully_connected(net, 1)
    out = tf.squeeze(out, axis=[1])
    return out


actor = Actor(actor_network_tflearn, actor_optimizer, sess, observation_shape, action_shape)
critic = Critic(critic_network_tflearn, critic_optimizer, sess, observation_shape, action_shape)
actor_noise = OrnsteinUhlenbeckActionNoise(mu=np.zeros(action_shape))

MAX_EPISODES = 10000
MAX_STEPS    = 200

sess.run(tf.global_variables_initializer())

episode_history = deque(maxlen=100)
memory_buffer = deque(maxlen=10000)
tot_rewards = deque(maxlen=10000)
for e in range(MAX_EPISODES):
  state = env.reset()
  cum_reward = 0
  ep_ave_max_q = 0
  tot_loss = 0
  for j in range(1000):
    action = actor.predict([state])[0] + actor_noise()
    next_state, reward, done, _ = env.step(action)
    cum_reward += reward
    tot_rewards.append(reward)
    memory_buffer.append((state, action, reward, next_state, done))

    if len(memory_buffer) > BATCH_SIZE:
      indices = np.random.choice(len(memory_buffer), BATCH_SIZE, replace=False)
      # indices = range(64)
      states, actions, rewards, next_states, dones = zip(*[memory_buffer[idx] for idx in indices])

      qprimes = critic.predict_target(next_states, actor.predict_target(next_states))
      # normalize rewards?
      # avg_reward = np.mean(tot_rewards)
      # rewards = [r + 9.0 for r in rewards]
      target_qs = [r + 0.99 * qp if not d else r for (r, qp, d) in zip(rewards, qprimes, dones)]
      qs, target_net_qs, qloss, _ = critic.train(states=states, 
        actions=actions, 
        target_qs=target_qs)
      # print target_net_qs
      # print qs
      # print np.mean(np.square(target_qs-qs)) - qloss
      # print qloss
      ep_ave_max_q += np.amax(qs)
      tot_loss += qloss
      predicted_actions = actor.predict(states)
      action_gradients = critic.get_action_gradients(states, predicted_actions)
      actor.train(states=states, action_gradients=action_gradients)

      # update targets
      actor.update_target()
      critic.update_target()

    if done:
      # train agent
      # print the score and break out of the loop
      episode_history.append(cum_reward)
      print("episode: {}/{}, score: {}, avg score for 100 runs: {:.2f}, maxQ: {:.2f}, avg loss: {:.5f}".format(e, MAX_EPISODES, cum_reward, np.mean(episode_history), ep_ave_max_q / float(j), tot_loss / float(j)))
      break
    state = next_state
